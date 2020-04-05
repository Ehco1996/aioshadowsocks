import asyncio
import logging
import socket
import struct

from shadowsocks import protocol_flag as flag
from shadowsocks import current_app
from shadowsocks.cryptor import Cryptor
from shadowsocks.utils import parse_header

from shadowsocks.metrics import (
    ACTIVE_CONNECTION_COUNT,
    CONNECTION_MADE_COUNT,
    NETWORK_TRANSMIT_BYTES,
)


class TimeoutMixin:
    TIMEOUT = current_app.timeout_limit

    def __init__(self):
        self.loop = asyncio.get_running_loop()
        self.timeout_handle = self.loop.call_later(self.TIMEOUT, self._timeout)

        self._need_clean = False

    def close(self):
        raise NotImplementedError

    def _timeout(self):
        self.close()
        self._need_clean = True

    def keep_alive(self):
        self.timeout_handle.cancel()
        self.timeout_handle = self.loop.call_later(self.TIMEOUT, self._timeout)

    @property
    def need_clean(self):
        return self._need_clean


class LocalHandler(TimeoutMixin):
    """
    事件循环一共处理五个状态

    STAGE_INIT  初始状态 socket5握手
    STAGE_CONNECT 连接建立阶段 从本地获取addr 进行dns解析
    STAGE_STREAM 建立管道(pipe) 进行socket5传输
    STAGE_DESTROY 结束连接状态
    STAGE_ERROR 异常状态
    """

    STAGE_INIT = 0
    STAGE_CONNECT = 1
    STAGE_STREAM = 2
    STAGE_DESTROY = -1
    STAGE_ERROR = 255

    def __init__(self, user):
        super().__init__()

        self.user = user
        self.server = user.server

        self._stage = None
        self._peername = None
        self._remote = None
        self._cryptor = None
        self._transport = None
        self._transport_protocol = None
        self._is_closing = False
        self._connect_buffer = bytearray()

    def _init_transport(self, transport, peername, protocol):
        self._stage = self.STAGE_INIT
        self._transport = transport
        self._peername = peername
        self._transport_protocol = protocol

    def _init_cryptor(self):
        try:
            self._cryptor = Cryptor(
                self.user.method, self.user.password, self._transport_protocol
            )
        except NotImplementedError:
            self.close()
            logging.warning("not support cipher")

    def close(self):
        if self._is_closing:
            return
        self._is_closing = True
        if self._transport_protocol == flag.TRANSPORT_TCP:
            self.server.incr_tcp_conn_num(-1)
            self._transport and self._transport.close()
            if self._remote:
                self._remote.close()
                # NOTE for circular reference
                self._remote = None
        elif self._transport_protocol == flag.TRANSPORT_UDP:
            pass
        else:
            raise NotImplementedError
        self._stage = self.STAGE_DESTROY

        ACTIVE_CONNECTION_COUNT.dec()

    def write(self, data):
        if not self._transport or self._transport.is_closing():
            self._transport and self._transport.abort()
            return
        if self._transport_protocol == flag.TRANSPORT_TCP:
            self._transport.write(data)
        elif self._transport_protocol == flag.TRANSPORT_UDP:
            # get the remote address to which the socket is connected
            self._transport.sendto(data, self._peername)
        else:
            raise NotImplementedError

    def handle_connection_made(self, transport_type, transport, peername):
        self._init_transport(transport, peername, transport_type)
        if transport_type == flag.TRANSPORT_TCP and self.server.limited:
            self.server.log_limited_msg()
            self.close()
        self._init_cryptor()

        CONNECTION_MADE_COUNT.inc()
        ACTIVE_CONNECTION_COUNT.inc()

    def handle_eof_received(self):
        self.close()
        logging.debug("eof received")

    def handle_connection_lost(self, exc):
        self.close()
        logging.debug(f"lost exc={exc}")

    def handle_data_received(self, data):
        try:
            data = self._cryptor.decrypt(data)
        except Exception as e:
            self.close()
            logging.warning(f"decrypt data error {e}")
            return

        if self._stage == self.STAGE_INIT:
            coro = self._handle_stage_init(data)
            asyncio.create_task(coro)
        elif self._stage == self.STAGE_CONNECT:
            coro = self._handle_stage_connect(data)
            asyncio.create_task(coro)
        elif self._stage == self.STAGE_STREAM:
            self._handle_stage_stream(data)
        elif self._stage == self.STAGE_ERROR:
            self._handle_stage_error()
        elif self._stage == self.STAGE_DESTROY:
            self.close()
        else:
            logging.warning(f"unknown stage:{self._stage}")

    async def _handle_stage_init(self, data):
        if not data:
            return

        addr_type, dst_addr, dst_port, header_length = parse_header(data)
        if not all([addr_type, dst_addr, dst_port, header_length]):
            logging.warning(f"parse error addr_type: {addr_type} user: {self.user}")
            self.close()
            return
        else:
            payload = data[header_length:]

        logging.debug(
            f"[HEADER:] {addr_type} {dst_addr}:{dst_port} - {self._transport_protocol}"
        )

        if self._transport_protocol == flag.TRANSPORT_TCP:
            self._stage = self.STAGE_CONNECT
            tcp_coro = self.loop.create_connection(
                lambda: RemoteTCP(dst_addr, dst_port, payload, self), dst_addr, dst_port
            )
            try:
                _, remote_tcp = await tcp_coro
            except (IOError, OSError) as e:
                self.close()
                self._stage = self.STAGE_DESTROY
                logging.debug(f"connection failed , {type(e)} e: {e}")
            except Exception as e:
                self._stage = self.STAGE_ERROR
                self.close()
                logging.warning(f"connection failed, {type(e)} e: {e}")
            else:
                self._remote = remote_tcp
                self._stage = self.STAGE_STREAM
                self._remote.write(self._connect_buffer)
                logging.debug(f"connection ok buffer lens：{len(self._connect_buffer)}")

        elif self._transport_protocol == flag.TRANSPORT_UDP:
            udp_coro = self.loop.create_datagram_endpoint(
                lambda: RemoteUDP(dst_addr, dst_port, payload, self),
                remote_addr=(dst_addr, dst_port),
            )
            try:
                await udp_coro
            except (IOError, OSError) as e:
                self.close()
                self._stage = self.STAGE_DESTROY
                logging.debug(f"connection failed , {type(e)} e: {e}")
            except Exception as e:
                self._stage = self.STAGE_ERROR
                self.close()
                logging.warning(f"connection failed, {type(e)} e: {e}")
        else:
            raise NotImplementedError

    async def _handle_stage_connect(self, data):
        # 在握手之后，会耗费一定时间来来和remote建立连接
        # 但是ss-client并不会等这个时间 把数据线放进buffer
        self._connect_buffer.extend(data)

    def _handle_stage_stream(self, data):
        self.keep_alive()
        self._remote.write(data)
        logging.debug(f"relay data length {len(data)}")

    def _handle_stage_error(self):
        self.close()


class LocalTCP(asyncio.Protocol):
    """
    Local Tcp Factory
    """

    def __init__(self, user):
        self._handler = None
        self.user = user
        self.server = user.server

    def _init_handler(self):
        if not self._handler:
            self._handler = LocalHandler(self.user)
        return self._handler

    def __call__(self):
        local = LocalTCP(self.user)
        local._init_handler()
        return local

    def pause_writing(self):
        try:
            self._handler._remote._transport.pause_reading()
        except AttributeError:
            pass

    def resume_writing(self):
        try:
            self._handler._remote._transport.resume_reading()
        except AttributeError:
            pass

    def connection_made(self, transport):
        self._transport = transport
        peername = self._transport.get_extra_info("peername")
        # NOTE 只记录 client->ss-local的ip和tcp_conn_num
        self.server.record_ip(peername)
        self.server.incr_tcp_conn_num(1)
        self._handler.handle_connection_made(flag.TRANSPORT_TCP, transport, peername)

    def data_received(self, data):
        self._handler.handle_data_received(data)
        self.server.record_traffic(used_u=len(data), used_d=0)

    def eof_received(self):
        self._handler.handle_eof_received()

    def connection_lost(self, exc):
        self._handler.handle_connection_lost(exc)


class LocalUDP(asyncio.DatagramProtocol):
    """
    Local Udp Factory
    """

    def __init__(self, user):
        self.user = user
        self.server = user.server
        self._protocols = {}
        self._transport = None

    def __call__(self):
        local = LocalUDP(self.user)
        return local

    def connection_made(self, transport):
        self._transport = transport

    def datagram_received(self, data, peername):
        if peername in self._protocols:
            handler = self._protocols[peername]
        else:
            handler = LocalHandler(self.user)
            self._protocols[peername] = handler
            handler.handle_connection_made(
                flag.TRANSPORT_UDP, self._transport, peername
            )

        handler.handle_data_received(data)
        self.server.record_traffic(used_u=len(data), used_d=0)
        self._clear_closed_handlers()

    def error_received(self, exc):
        pass

    def _clear_closed_handlers(self):
        logging.debug(f"now udp handler {len(self._protocols)}")
        need_clear_peers = []
        for peername, handler in self._protocols.items():
            if handler.need_clean:
                need_clear_peers.append(peername)
        for peer in need_clear_peers:
            del self._protocols[peer]
        logging.debug(f"after clear {len(self._protocols)}")


class RemoteTCP(asyncio.Protocol, TimeoutMixin):
    def __init__(self, addr, port, data, local_handler):
        super().__init__()

        self.data = data
        self.local = local_handler
        self.cryptor = Cryptor(
            self.local.user.method, self.local.user.password, flag.TRANSPORT_TCP
        )

        self.peername = None
        self._transport = None
        self.loop = asyncio.get_running_loop()

    def write(self, data):
        if not self._transport or self._transport.is_closing():
            self._transport and self._transport.abort()
            return

        self._transport.write(data)

    def close(self):
        self._transport and self._transport.close()
        # NOTE for circular reference
        self.data = None
        self.local = None

    def connection_made(self, transport):
        self._transport = transport
        self.peername = self._transport.get_extra_info("peername")
        self.write(self.data)

    def data_received(self, data):
        self.keep_alive()
        server = self.local.server
        server.record_traffic_rate(len(data))
        server.record_traffic(used_u=0, used_d=len(data))
        self.local.write(self.cryptor.encrypt(data))
        if server.traffic_limiter.limited:
            self.pause_reading()
            t = server.traffic_limiter.get_sleep_time()
            self.loop.call_later(t, self.resume_reading)

        NETWORK_TRANSMIT_BYTES.inc(len(data))

    def pause_reading(self):
        if self._transport:
            self._transport.pause_reading()

    def resume_reading(self):
        if self._transport:
            self._transport.resume_reading()

    def eof_received(self):
        # NOTE tell ss-local
        self.local and self.local.handle_eof_received()
        self.close()

    def connection_lost(self, exc):
        self.close()


class RemoteUDP(asyncio.DatagramProtocol, TimeoutMixin):
    def __init__(self, addr, port, data, local_hander):
        super().__init__()
        self.data = data
        self.local = local_hander
        self.cryptor = Cryptor(
            self.local.user.method, self.local.user.password, flag.TRANSPORT_UDP
        )

        self.peername = None
        self._transport = None

    def write(self, data):
        self._transport and self._transport.sendto(data, self.peername)

    def close(self):
        self._transport and self._transport.close()
        # NOTE for circular reference
        self.data = None
        self.local = None

    def connection_made(self, transport):
        self._transport = transport
        self.peername = self._transport.get_extra_info("peername")
        self.write(self.data)

    def datagram_received(self, data, peername, *arg):
        self.keep_alive()

        assert self.peername == peername
        # 源地址和端口
        bind_addr = peername[0]
        bind_port = peername[1]
        if "." in bind_addr:
            addr = socket.inet_pton(socket.AF_INET, bind_addr)
        elif ":" in bind_addr:
            addr = socket.inet_pton(socket.AF_INET6, bind_addr)
        else:
            raise Exception("add not valid")
        port = struct.pack("!H", bind_port)
        # 构造返回的报文结构
        data = b"\x01" + addr + port + data
        data = self.cryptor.encrypt(data)
        self.local.server.record_traffic(used_u=0, used_d=len(data))
        self.local.write(data)

        NETWORK_TRANSMIT_BYTES.inc(len(data))

    def error_received(self, exc):
        logging.debug("error received exc {}".format(exc))
        self.close()

    def connection_lost(self, exc):
        logging.debug("udp connetcion lost exc {}".format(exc))
        self.close()
