import asyncio

from shadowsocks.handlers import BaseTimeoutHandler


class RemoteTCP(asyncio.Protocol, BaseTimeoutHandler):

    def __init__(self, addr, port, data, key, local_handler):
        pass
