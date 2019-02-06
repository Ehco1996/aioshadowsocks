import logging
import asyncio

from shadowsocks.cryptor import Cryptor
from shadowsocks import protocol_flag as flag
from shadowsocks.handlers import LocalHandler, TimeoutHandler


class LocalTCP(asyncio.Protocol):
    def __init__(self, user):
        self._handler = None
        self.user = user

    def _init_handler(self):
        self._handler = LocalHandler(self.user.method, self.user.password, self.user)

    def __call__(self):
        local = LocalTCP(self.user)
        local._init_handler()
        return local

    def connection_made(self, transport):
        self._handler.handle_tcp_connection_made(transport)
        self.user.ip_list.add(transport.get_extra_info("peername")[0])

    def data_received(self, data):
        self._handler.handle_data_received(data)

    def eof_received(self):
        self._handler.handle_eof_received()

    def connection_lost(self, exc):
        self._handler.handle_connection_lost(exc)


class RemoteTCP(asyncio.Protocol, TimeoutHandler):
    def __init__(self, addr, port, data, method, password, local_handler):
        TimeoutHandler.__init__(self)
        self._data = data
        self._local = local_handler
        self._peername = None
        self._transport = None
        self._transport_type = flag.TRANSPORT_TCP
        self._cryptor = Cryptor(method, password, self._transport_type)

    def write(self, data):
        if self._transport:
            self._transport.write(data)

    def close(self):
        if self._transport is not None:
            self._transport.close()

    def connection_made(self, transport):
        self.keep_alive_open()
        self._transport = transport
        self._peername = self._transport.get_extra_info("peername")
        logging.debug(
            "remotetcp connection made, peername {} user: {}".format(
                self._peername, self._local.user
            )
        )
        self.write(self._data)

    def data_received(self, data):
        if self._local_verified is False:
            self.close()
            return
        self.keep_alive_active()
        logging.debug(
            "remotetcp {} received data length: {} user: {}".format(
                self, len(data), self._local.user
            )
        )
        data = self._cryptor.encrypt(data)
        self._local.write(data)

    def eof_received(self):
        logging.debug("eof received")
        self.close()

    def connection_lost(self, exc):
        logging.debug("lost exc={exc}".format(exc=exc))
        if self._local is not None:
            self._local.close()

    @property
    def _local_verified(self):
        if not self._local:
            return False
        elif self._local._transport is None:
            return False
        elif self._transport._sock is None:
            # cpython selector_events _SelectorTransport
            return False
        return True
