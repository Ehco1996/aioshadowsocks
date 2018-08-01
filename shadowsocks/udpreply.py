import asyncio

from shadowsocks.handlers import BaseTimeoutHandler


class RemoteUDP(asyncio.DatagramProtocol, BaseTimeoutHandler):

    def __init__(self, addr, port, data, key, local_hander):
        pass
