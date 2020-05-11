import asyncio
import logging
import socket
import struct

from shadowsocks import protocol_flag as flag
from shadowsocks.cipherman import CipherMan
from shadowsocks.metrics import ACTIVE_CONNECTION_COUNT, CONNECTION_MADE_COUNT
from shadowsocks.utils import parse_header


class TimeoutMixin:
    TIMEOUT = 60  # TODO 变成可以配置的

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

    def __init__(self, port):
        super().__init__()

        self.port = port
        self.cipher = None

        self._stage = None
        self._peername = None
        self._remote = None
        self._transport = None
        self._transport_protocol = None
        self._transport_protocol_human = None
        self._is_closing = False
        self._connect_buffer = bytearray()

    def _init_transport(self, transport, peername, protocol):
        self._stage = self.STAGE_INIT
        self._transport = transport
        self._peername = peername
        self._transport_protocol = protocol
        if protocol == flag.TRANSPORT_TCP:
            self._transport_protocol_human = "tcp"
        else:
            self._transport_protocol_human = "udp"

    def _init_cipher(self):
        self.cipher = CipherMan.get_cipher_by_port(self.port, self._transport_protocol)

    def close(self):
        if self._is_closing:
            return
        self._is_closing = True

        if self._transport_protocol == flag.TRANSPORT_TCP:
            self._transport and self._transport.close()
            self._remote and self._remote.close()
            self.cipher and self.cipher.incr_user_tcp_num(-1)
        elif self._transport_protocol == flag.TRANSPORT_UDP:
            pass
        self._stage = self.STAGE_DESTROY
        ACTIVE_CONNECTION_COUNT.inc(-1)

    def write(self, data):
        if self._transport_protocol == flag.TRANSPORT_TCP:
            self._transport and not self._transport.is_closing() and self._transport.write(
                data
            )
        else:
            self._transport and not self._transport.is_closing() and self._transport.sendto(
                data, self._peername
            )

    def handle_connection_made(self, transport_protocol, transport, peername):
        self._init_transport(transport, peername, transport_protocol)
        self._init_cipher()
        ACTIVE_CONNECTION_COUNT.inc()
        CONNECTION_MADE_COUNT.inc()

    def handle_eof_received(self):
        self.close()

    def handle_connection_lost(self, exc):
        self.close()

    def handle_data_received(self, data):

        try:
            data = self.cipher.decrypt(data)
        except Exception as e:
            self.close()
            logging.warning(
                f"decrypt data error:{e} remote:{self._peername},type:{self._transport_protocol_human} closing..."
            )
            return

        if not data:
            return

        if self._stage == self.STAGE_INIT:
            asyncio.create_task(self._handle_stage_init(data))
        elif self._stage == self.STAGE_CONNECT:
            self._handle_stage_connect(data)
        elif self._stage == self.STAGE_STREAM:
            self._handle_stage_stream(data)
        elif self._stage == self.STAGE_ERROR:
            self.close()
        elif self._stage == self.STAGE_DESTROY:
            self.close()
        else:
            logging.warning(f"unknown stage:{self._stage}")

    async def _handle_stage_init(self, data):
        addr_type, dst_addr, dst_port, header_length = parse_header(data)
        if not all([addr_type, dst_addr, dst_port, header_length]):
            logging.warning(f"parse error addr_type: {addr_type} port: {self.port}")
            self.close()
            return
        else:
            payload = data[header_length:]

        logging.debug(
            f"HEADER: {addr_type} - {dst_addr} - {dst_port} - {self._transport_protocol}"
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
                self.cipher and self.cipher.incr_user_tcp_num(1)
                self.cipher and self.cipher.record_user_ip(self._peername)

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

    def _handle_stage_connect(self, data):
        # 在握手之后，会耗费一定时间来来和remote建立连接,但是ss-client并不会等这个时间
        self._connect_buffer.extend(data)

    def _handle_stage_stream(self, data):
        self.keep_alive()
        self._remote.write(data)
        logging.debug(f"relay data length {len(data)}")


class LocalTCP(asyncio.Protocol):
    """
    Local Tcp Factory
    """

    def __init__(self, port):
        self.port = port
        self._handler = None

    def _init_handler(self):
        self._handler = LocalHandler(self.port)

    def __call__(self):
        local = LocalTCP(self.port)
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
        self._handler.handle_connection_made(flag.TRANSPORT_TCP, transport, peername)

    def data_received(self, data):
        self._handler.handle_data_received(data)

    def eof_received(self):
        self._handler.handle_eof_received()

    def connection_lost(self, exc):
        self._handler.handle_connection_lost(exc)


class LocalUDP(asyncio.DatagramProtocol):
    """
    Local Udp Factory
    """

    def __init__(self, port):
        self.port = port
        self._protocols = {}
        self._transport = None

    def __call__(self):
        local = LocalUDP(self.port)
        return local

    def connection_made(self, transport):
        self._transport = transport

    def datagram_received(self, data, peername):
        if peername in self._protocols:
            handler = self._protocols[peername]
        else:
            handler = LocalHandler(self.port)
            self._protocols[peername] = handler
            handler.handle_connection_made(
                flag.TRANSPORT_UDP, self._transport, peername
            )

        handler.handle_data_received(data)
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
        self.peername = None
        self._transport = None
        self.cipher = CipherMan(access_user=local_handler.cipher.access_user)

        self._is_closing = True

    def write(self, data):
        self._transport and not self._transport.is_closing() and self._transport.write(
            data
        )

    def close(self):
        if self._is_closing:
            return
        self._is_closing = True

        self._transport and self._transport.close()
        del self.local

    def connection_made(self, transport):
        self._transport = transport
        self.peername = self._transport.get_extra_info("peername")
        self.write(self.data)

    def data_received(self, data):
        self.keep_alive()
        self.local.write(self.cipher.encrypt(data))

    def pause_reading(self):
        self._transport and self._transport.pause_reading()

    def resume_reading(self):
        self._transport and self._transport.resume_reading()

    def eof_received(self):
        self.local and self.local.handle_eof_received()
        self.close()

    def connection_lost(self, exc):
        self.close()


class RemoteUDP(asyncio.DatagramProtocol, TimeoutMixin):
    def __init__(self, addr, port, data, local_hander):
        super().__init__()
        self.data = data
        self.local = local_hander
        self.peername = None
        self._transport = None
        self.cipher = CipherMan(
            access_user=self.local.cipher.access_user, ts_protocol=flag.TRANSPORT_UDP
        )
        self._is_closing = False

    def write(self, data):
        self._transport and not self._transport.is_closing() and self._transport.sendto(
            data
        )

    def close(self):
        if self._is_closing:
            return
        self._is_closing = True

        self._transport and self._transport.close()
        del self.local

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
        data = self.cipher.encrypt(data)
        self.local.write(data)

    def error_received(self, exc):
        self.close()

    def connection_lost(self, exc):
        self.close()
