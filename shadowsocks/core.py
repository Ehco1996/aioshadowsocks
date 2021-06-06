import asyncio
import logging
import socket
import struct
import time

from shadowsocks import protocol_flag as flag
from shadowsocks.cipherman import CipherMan
from shadowsocks.metrics import ACTIVE_CONNECTION_COUNT, CONNECTION_MADE_COUNT
from shadowsocks.utils import parse_header


class LocalHandler:
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
        self._is_closing = False
        self._connect_buffer = bytearray()

    def close(self):
        self._stage = self.STAGE_DESTROY
        if self._is_closing:
            return
        self._is_closing = True

        if self._transport_protocol == flag.TRANSPORT_TCP:
            ACTIVE_CONNECTION_COUNT.inc(-1)
            self.cipher and self.cipher.close()
            self._transport and self._transport.close()

        self._remote and self._remote.close()

    def write(self, data):
        if self._transport_protocol == flag.TRANSPORT_TCP:
            if self._transport.is_closing():
                return
            self._transport.write(data)
        else:
            self._transport.sendto(data, self._peername)

    def handle_connection_made(self, transport, peername, protocol):
        self._stage = self.STAGE_INIT
        self._transport = transport
        self._peername = peername
        self._transport_protocol = protocol

    def handle_eof_received(self):
        self.close()

    def handle_connection_lost(self, exc):
        self.close()

    def handle_data_received(self, data):
        if not self.cipher or self._transport_protocol == flag.TRANSPORT_UDP:
            self.cipher = CipherMan.get_cipher_by_port(
                self.port, self._transport_protocol, self._peername
            )

        try:
            data = self.cipher.decrypt(data)
        except Exception as e:
            logging.warning(
                f"decrypt data error:{e} remote:{self._peername},type:{self._transport_protocol}"
            )
            self.close()
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
            self.close()

    async def _handle_stage_init(self, data):
        atype, dst_addr, dst_port, header_length = parse_header(data)
        if not all([atype, dst_addr, dst_port, header_length]):
            logging.warning(
                f"parse_header_error atype={flag.get_atype_for_human(atype)} port={self.port}"
            )
            self.close()
            return
        else:
            logging.info(
                "parse_header_success flag={} atype={} from={} dst={}:{}".format(
                    self._transport_protocol,
                    flag.get_atype_for_human(atype),
                    f"{self._peername[0]}:{self._peername[1]}",
                    dst_addr,
                    dst_port,
                )
            )
            payload = data[header_length:]

        loop = asyncio.get_running_loop()
        if self._transport_protocol == flag.TRANSPORT_TCP:
            self._stage = self.STAGE_CONNECT
            self._handle_stage_connect(payload)
            try:
                task = loop.create_connection(
                    lambda: RemoteTCP(self), dst_addr, dst_port
                )
                _, remote_tcp = await asyncio.wait_for(task, 5)
            except Exception as e:
                self._stage = self.STAGE_ERROR
                self.close()
                logging.warning(
                    f"connection_failed, {type(e)} e: {dst_addr}:{dst_port}"
                )
            else:
                self._remote = remote_tcp
        else:
            try:
                task = loop.create_datagram_endpoint(
                    lambda: RemoteUDP(dst_addr, dst_port, payload, self),
                    remote_addr=(dst_addr, dst_port),
                )
                _, remote_udp = await asyncio.wait_for(task, 5)
            except Exception as e:
                self._stage = self.STAGE_ERROR
                logging.warning(
                    f"connection_failed, {type(e)} e: {dst_addr}:{dst_port}"
                )
                self.close()
            else:
                self._remote = remote_udp
                self._stage = self.STAGE_STREAM

    def _handle_stage_connect(self, data):
        # 在握手之后，会耗费一定时间来来和remote建立连接,但是ss-client并不会等这个时间
        if not self._remote or self._remote.ready == False:
            self._connect_buffer.extend(data)
        else:
            self._stage = self.STAGE_STREAM
            self._handle_stage_stream(data)

    def _handle_stage_stream(self, data):
        if self._transport_protocol == flag.TRANSPORT_UDP:
            # NOTE 区分udp和tcp，tcp的可以直接转发，udp的需要去掉header
            _, _, _, header_length = parse_header(data)
            data = data[header_length:]
        self._remote.write(data)


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
        # NOTE remote may not init
        try:
            self._handler._remote._transport.pause_reading()
        except AttributeError:
            pass

    def resume_writing(self):
        self._handler._remote._transport.resume_reading()

    def connection_made(self, transport):
        self._transport = transport
        peername = self._transport.get_extra_info("peername")
        self._handler.handle_connection_made(transport, peername, flag.TRANSPORT_TCP)
        CONNECTION_MADE_COUNT.inc()
        ACTIVE_CONNECTION_COUNT.inc()

    def data_received(self, data):
        self._handler.handle_data_received(data)

    def eof_received(self):
        self._handler.handle_eof_received()

    def connection_lost(self, exc):
        self._handler.handle_connection_lost(exc)


class RemoteTCP(asyncio.Protocol):
    def __init__(self, local_handler):
        super().__init__()

        self.local = local_handler
        self.peername = None
        self._transport = None
        self.ready = False

        self._is_closing = False

    def write(self, data):
        if not self._transport.is_closing():
            self._transport.write(data)

    def close(self):
        if self._is_closing:
            return
        self._is_closing = True
        ACTIVE_CONNECTION_COUNT.inc(-1)

        self._transport and self._transport.close()
        self.local.close()

    def connection_made(self, transport: asyncio.Transport):
        self._transport = transport
        self.peername = self._transport.get_extra_info("peername")
        self.cipher = CipherMan(
            access_user=self.local.cipher.access_user, peername=self.peername
        )
        transport.write(self.local._connect_buffer)
        self.ready = True
        CONNECTION_MADE_COUNT.inc()
        ACTIVE_CONNECTION_COUNT.inc()

    def data_received(self, data):
        self.local.write(self.cipher.encrypt(data))

    def pause_reading(self):
        self.local._transport.pause_reading()

    def resume_reading(self):
        self.local._transport.resume_reading()

    def eof_received(self):
        self.close()

    def connection_lost(self, exc):
        self.close()


class LocalUDP(asyncio.DatagramProtocol):
    """
    Local Udp Factory
    """

    def __init__(self, port):
        self.port = port
        self.udpmap = {}
        self._transport = None

    def __call__(self):
        return LocalUDP(self.port)

    def connection_made(self, transport):
        self._transport = transport

    def datagram_received(self, data, peername):
        if peername in self.udpmap:
            handler = self.udpmap[peername]
        else:
            handler = LocalHandler(self.port)
            self.udpmap[peername] = handler
            handler.handle_connection_made(
                self._transport, peername, flag.TRANSPORT_UDP
            )
        handler.handle_data_received(data)
        # NOTE 注入这个udp上次使用的时间
        handler.last_use_time = time.time()
        self.clean_udpmap()

    def clean_udpmap(self):
        now = time.time()
        need_delete = [
            peer
            for peer, handler in self.udpmap.items()
            if now - handler.last_use_time > 1
        ]

        if not need_delete:
            return
        for peer in need_delete:
            h = self.udpmap.pop(peer)
            h.close()
        logging.info(f"clean udpmap peer delete={need_delete}")

    def error_received(self, exc) -> None:
        return super().error_received(exc)

    def connection_lost(self, exc) -> None:
        return super().connection_lost(exc)


class RemoteUDP(asyncio.DatagramProtocol):
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
        self.local = None

    def connection_made(self, transport):
        self._transport = transport
        self.peername = self._transport.get_extra_info("peername")
        self.write(self.data)

    def datagram_received(self, data, peername, *arg):
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
