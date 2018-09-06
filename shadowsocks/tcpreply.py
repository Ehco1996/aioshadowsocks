import logging
import asyncio

from shadowsocks.cryptor import Cryptor
from shadowsocks import protocol_flag as flag
from shadowsocks.handlers import BaseTimeoutHandler, LocalHandler


class LocalTCP(asyncio.Protocol):
    '''
    Interface for stream protocol.

    The user should implement this interface.  They can inherit from
    this class but don't need to.  The implementations here do
    nothing (they don't raise exceptions).

    When the user wants to requests a transport, they pass a protocol
    factory to a utility function (e.g., EventLoop.create_connection()).

    When the connection is made successfully, connection_made() is
    called with a suitable transport object.  Then data_received()
    will be called 0 or more times with data (bytes) received from the
    transport; finally, connection_lost() will be called exactly once
    with either an exception object or None as an argument.

    State machine of calls:

      start -> CM [-> DR*] [-> ER?] -> CL -> end

    * CM: connection_made()
    * DR: data_received()
    * ER: eof_received()
    * CL: connection_lost()
    '''

    def __init__(self, user):
        self.user = user
        self._handler = None

    def _init_handler(self, user):
        self._handler = LocalHandler(user.method, user.password, user)

    def __call__(self):
        local = LocalTCP(self.user)
        local._init_handler(self.user)
        return local

    def connection_made(self, transport):
        '''
        Called when a connection is made.

        The argument is the transport representing the pipe connection.
        To receive data, wait for data_received() calls.
        When the connection is closed, connection_lost() is called.
        '''
        self._handler.handle_tcp_connection_made(transport)

    def data_received(self, data):
        '''
        Called when some data is received.
        The argument is a bytes object.
        '''
        self._handler.handle_data_received(data)

    def eof_received(self):
        '''
        Called when the other end calls write_eof() or equivalent.

        If this returns a false value (including None), the transport
        will close itself.  If it returns a true value, closing the
        transport is up to the protocol.
        '''
        self._handler.handle_eof_received()

    def connection_lost(self, exc):
        '''
        Called when the connection is lost or closed.

        The argument is an exception object or None (the latter
        meaning a regular EOF is received or the connection was
        aborted or closed).
        '''
        self._handler.handle_connection_lost(exc)


class RemoteTCP(asyncio.Protocol, BaseTimeoutHandler):

    def __init__(self, addr, port, data, method, password, local_handler):
        BaseTimeoutHandler.__init__(self)

        self._logger = logging.getLogger(
            '<RemoteTCP{} {}>'.format((addr, port), hex(id(self))))
        self._data = data
        self._local = local_handler
        self._peername = None
        self._transport = None
        self._transport_type = flag.TRANSPORT_TCP
        self._cryptor = Cryptor(method, password)

    def write(self, data):
        if self._transport is not None:
            self._transport.write(data)

    def close(self):
        if self._transport is not None:
            self._transport.close()

    def connection_made(self, transport):
        self.keep_alive_active()

        self._transport = transport
        self._peername = self._transport.get_extra_info('peername')
        self._logger.debug(
            'connection made, peername {}'.format(self._peername))
        self.write(self._data)

    def data_received(self, data):
        self.keep_alive_active()
        # 记录下载流量
        self._local.user.once_used_d += len(data)

        self._logger.debug('received data length: {}'.format(len(data)))
        data = self._cryptor.encrypt(data)
        self._local.write(data)

    def eof_received(self):
        self._logger.debug('eof received')
        self.close()

    def connection_lost(self, exc):
        self._logger.debug('lost exc={exc}'.format(exc=exc))
        if self._local is not None:
            self._local.close()
