import os
import socket
import struct
import asyncio
import logging
import time

from shadowsocks import protocol_flag as flag
from shadowsocks.cryptor import Cryptor
from shadowsocks.utils import parse_header


class TimeoutHandler:
    def __init__(self):
        self._transport = None
        self._last_active_time = time.time()
        self._timeout_limit = os.getenv("SS_TIME_OUT_LIMIT", 60)

    def close(self):
        raise NotImplementedError

    def check_conn_timeout(self):
        asyncio.create_task(self._check_conn_timeout())

    def keep_alive_active(self):
        self._last_active_time = time.time()

    async def _check_conn_timeout(self):
        while True:
            current_time = time.time()
            if current_time - self._last_active_time > self._timeout_limit:
                self.close()
                break
            else:
                await asyncio.sleep(2)


class LocalHandler(TimeoutHandler):
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
        TimeoutHandler.__init__(self)

        self.user = user

        self._stage = self.STAGE_DESTROY
        self._peername = None
        self._remote = None
        self._cryptor = None
        self._transport = None
        self._transport_protocol = None

    def _init_transport_and_cryptor(self, transport, peername, protocol):
        self._stage = self.STAGE_INIT
        self._transport = transport
        self._peername = peername
        self._transport_protocol = protocol

        try:
            self._cryptor = Cryptor(
                self.user.method, self.user.password, self._transport_protocol
            )
            logging.debug("tcp connection made")
        except NotImplementedError:
            self.close()
            logging.warning("not support cipher")

    def close(self):
        if self._transport_protocol == flag.TRANSPORT_TCP:
            self._transport and self._transport.close()
        elif self._transport_protocol == flag.TRANSPORT_UDP:
            pass
        else:
            raise NotImplementedError

    def write(self, data):
        if not self._transport or self._transport.is_closing():
            self._transport and self._transport.abort()
            return

        self.user.server.record_traffic(used_u=0, used_d=len(data))

        if self._transport_protocol == flag.TRANSPORT_TCP:
            self._transport.write(data)
        elif self._transport_protocol == flag.TRANSPORT_UDP:
            # get the remote address to which the socket is connected
            self._transport.sendto(data, self._peername)
        else:
            raise NotImplementedError

    def handle_tcp_connection_made(self, transport, peername):
        self._init_transport_and_cryptor(transport, peername, flag.TRANSPORT_TCP)
        self.check_conn_timeout()
        self.user.server.record_ip(peername)

    def handle_udp_connection_made(self, transport, peername):
        self._init_transport_and_cryptor(transport, peername, flag.TRANSPORT_UDP)
        self.user.server.record_ip(peername)

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
        self.user.server.record_traffic(used_u=len(data), used_d=0)

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
        else:
            logging.warning(f"unknown stage:{self._stage}")

    async def _handle_stage_init(self, data):
        try:
            addr_type, dst_addr, dst_port, header_length = parse_header(data)
        except Exception as e:
            self.close()
            logging.warning(f"parse header error: {str(e)}")
            return
        if not dst_addr:
            self.close()
            logging.warning(
                "can't parse addr_type: {} user: {} CMD: {}".format(
                    addr_type, self.user, self._transport_protocol
                )
            )
            return
        else:
            payload = data[header_length:]
        loop = asyncio.get_event_loop()
        if self._transport_protocol == flag.TRANSPORT_TCP:
            self._stage = self.STAGE_CONNECT

            # 尝试建立tcp连接，成功的话将会返回 (transport,protocol)
            tcp_coro = loop.create_connection(
                lambda: RemoteTCP(dst_addr, dst_port, payload, self), dst_addr, dst_port
            )
            try:
                remote_transport, remote_tcp = await tcp_coro
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
                logging.debug(f"connection established,remote {remote_tcp}")
        elif self._transport_protocol == flag.TRANSPORT_UDP:
            self._stage = self.STAGE_INIT
            udp_coro = loop.create_datagram_endpoint(
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
        # 但是ss-client并不会等这个时间 所以我们在这里手动sleep一会
        sleep_time = 0.3
        for i in range(10):
            sleep_time += 0.1
            if self._stage == self.STAGE_CONNECT:
                await asyncio.sleep(sleep_time)
            elif self._stage == self.STAGE_STREAM:
                self._remote.write(data)
                return
        self.close()
        logging.warning(
            f"timeout to connect remote user: {self.user} peername: {self._peername}"
        )

    def _handle_stage_stream(self, data):
        self.keep_alive_active()
        self._remote.write(data)
        logging.debug(f"relay data length {len(data)}")

    def _handle_stage_error(self):
        self.close()


class LocalTCP(asyncio.Protocol):
    def __init__(self, user):
        self._handler = None
        self.user = user

    def _init_handler(self):
        self._handler = LocalHandler(self.user)

    def __call__(self):
        local = LocalTCP(self.user)
        local._init_handler()
        return local

    def connection_made(self, transport):
        self._transport = transport
        peername = self._transport.get_extra_info("peername")
        self._handler.handle_tcp_connection_made(transport, peername)

    def data_received(self, data):
        self._handler.handle_data_received(data)

    def eof_received(self):
        self._handler.handle_eof_received()

    def connection_lost(self, exc):
        self._handler.handle_connection_lost(exc)


class LocalUDP(asyncio.DatagramProtocol):
    def __init__(self, user):
        self.user = user
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
            handler.handle_udp_connection_made(self._transport, peername)
        handler.handle_data_received(data)

    def error_received(self, exc):
        pass


class RemoteTCP(asyncio.Protocol, TimeoutHandler):
    def __init__(self, addr, port, data, local_handler):
        TimeoutHandler.__init__(self)

        self.data = data
        self.local = local_handler
        self.cryptor = Cryptor(
            self.local.user.method, self.local.user.password, flag.TRANSPORT_TCP
        )

        self.peername = None
        self._transport = None

    def write(self, data):
        if not self._transport or self._transport.is_closing():
            self._transport and self._transport.abort()
            return
        self._transport.write(data)

    def close(self):
        self._transport and self._transport.close()

    def connection_made(self, transport):
        self.check_conn_timeout()

        self._transport = transport
        self.peername = self._transport.get_extra_info("peername")
        self.write(self.data)
        logging.debug(
            f"remote_tcp connection made, addr: {self.peername} user: {self.local.user}"
        )

    def data_received(self, data):
        self.keep_alive_active()
        self.local.write(self.cryptor.encrypt(data))
        logging.debug(
            f"remote_tcp {self} received data len: {len(data)} user: {self.local.user}"
        )

    def eof_received(self):
        self.close()
        logging.debug("eof received")

    def connection_lost(self, exc):
        self.close()
        logging.debug("lost exc={exc}".format(exc=exc))


class RemoteUDP(asyncio.DatagramProtocol, TimeoutHandler):
    def __init__(self, addr, port, data, local_hander):
        TimeoutHandler.__init__(self)
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

    def connection_made(self, transport):
        self.check_conn_timeout()
        self._transport = transport
        self.peername = self._transport.get_extra_info("peername")
        self.write(self.data)
        logging.debug(
            f"remote_udp connection made, addr: {self.peername} user: {self.local.user}"
        )

    def datagram_received(self, data, peername, *arg):
        self.keep_alive_active()

        logging.debug(
            f"remote_udp {self} received data len: {len(data)} user: {self.local.user}"
        )

        assert self.peername == peername
        # 源地址和端口
        bind_addr, bind_port = peername
        addr = socket.inet_pton(socket.AF_INET, bind_addr)
        port = struct.pack("!H", bind_port)
        # 构造返回的报文结构
        data = b"\x01" + addr + port + data
        data = self.cryptor.encrypt(data)
        self.local.write(data)

    def error_received(self, exc):
        logging.debug("error received exc {}".format(exc))

    def connection_lost(self, exc):
        logging.debug("udp connetcion lost exc {}".format(exc))
