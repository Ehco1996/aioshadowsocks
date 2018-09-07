import socket
import struct
import logging
import asyncio

from shadowsocks.cryptor import Cryptor
from shadowsocks.handlers import LocalHandler


class LoaclUDP(asyncio.DatagramProtocol):

    def __init__(self, user):
        self.user = user

    def _init_instance(self, user):
        self._instance = {}
        self._method = user.method
        self._password = user.password

    def __call__(self):
        local = LoaclUDP(self.user)
        local._init_instance(self.user)
        return local

    def connection_made(self, transport):
        self._transport = transport

    def datagram_received(self, data, peername):
        if peername in self._instance:
            handler = self._instance[peername]
        else:
            handler = LocalHandler(
                self._method, self._password, self.user)
            self._instance[peername] = handler
            handler.handle_udp_connection_made(self._transport, peername)
        handler.handle_data_received(data)

    def error_received(self, exc):
        '''
        Called when a send or receive operation raises an OSError.
        (Other than BlockingIOError or InterruptedError.)
        '''
        pass


class RemoteUDP(asyncio.DatagramProtocol):

    def __init__(self, addr, port, data, method, password, local_hander):
        self._logger = logging.getLogger(
            "<RemoteUDP{} {}>".format((addr, port), hex(id(self))))
        self._data = data
        self._local = local_hander
        self._peername = None
        self._transport = None
        self._cryptor = Cryptor(method, password)

    def write(self, data):
        if self._transport is not None:
            self._transport.sendto(data, self._peername)

    def close(self):
        if self._transport is not None:
            self._transport.close()

    def connection_made(self, transport):
        self._transport = transport
        self._peername = self._transport.get_extra_info('peername')
        self._logger.debug(
            "connetcion made peername: {}".format(self._peername))

    def connection_lost(self, exc):
        self._logger.debug("connetcion lost exc {}".format(exc))

    def datagram_received(self, data, peername):
        self._logger.debug("received data len: {}".format(len(data)))
        # 记录下载流量
        self._local.user.once_used_d += len(data)

        assert self._peername == peername
        # 源地址和端口
        bind_addr, bind_port = peername
        addr = socket.inet_pton(socket.AF_INET, bind_addr)
        port = struct.pack('!H', bind_port)
        # 构造返回的报文结构
        data = b'\x01' + addr + port + data
        data = self._cryptor.encrypt(data)
        self._local.write(data)

    def error_received(self, exc):
        self._logger.debug("error received exc {}".format(exc))
