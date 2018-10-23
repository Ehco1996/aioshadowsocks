import socket
import struct
import logging
import asyncio

from shadowsocks.cryptor import Cryptor
from shadowsocks.server_pool import ServerPool
from shadowsocks.handlers import LocalHandler, TimeoutHandler


class LocalUDP(asyncio.DatagramProtocol):

    def __init__(self, user_id):
        self.user_id = user_id
        self.pool = ServerPool()
        self.user = self.pool.get_user_by_id(self.user_id)

    def _init_instance(self):
        self._instance = {}
        self._method = self.user.method
        self._password = self.user.password

    def __call__(self):
        local = LocalUDP(self.user_id)
        local._init_instance()
        return local

    def connection_made(self, transport):
        self._transport = transport

    def datagram_received(self, data, peername):
        if peername in self._instance:
            handler = self._instance[peername]
        else:
            handler = LocalHandler(
                self._method, self._password, self.user_id)
            self._instance[peername] = handler
            handler.handle_udp_connection_made(self._transport, peername)
        handler.handle_data_received(data)

    def error_received(self, exc):
        '''
        Called when a send or receive operation raises an OSError.
        (Other than BlockingIOError or InterruptedError.)
        '''
        pass


class RemoteUDP(asyncio.DatagramProtocol, TimeoutHandler):

    def __init__(self, addr, port, data, method, password, local_hander):
        TimeoutHandler.__init__(self)
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
        self.keep_alive_open()
        self._transport = transport
        self._peername = self._transport.get_extra_info('peername')
        logging.debug("connetcion made peername: {} user: {}".format(
            self._peername, self._local.user))

    def connection_lost(self, exc):
        logging.debug("udp connetcion lost exc {}".format(exc))

    def datagram_received(self, data, peername):
        self.keep_alive_active()
        logging.debug("udp received data len: {} user: {}".format(
            len(data), self._local.user))
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
        logging.debug("error received exc {}".format(exc))
