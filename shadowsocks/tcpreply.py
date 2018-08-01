import asyncio

from shadowsocks.local_handler import LocalHandler
from shadowsocks.handlers import BaseTimeoutHandler


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

    def __init__(self, method, password):
        self._handler = LocalHandler(method, password)

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

    def __init__(self, addr, port, data, key, local_handler):
        pass
