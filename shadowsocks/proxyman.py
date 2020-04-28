import asyncio
import logging

from collections import defaultdict

from shadowsocks import current_app
from shadowsocks.core import LocalTCP, LocalUDP
from shadowsocks.mdb.models import User, UserServer


class ProxyMan:
    """
    1. 将model的调用都放在这里
    2. server相关的东西也放在这里
    app -> proxyman -> core ->cipherman/model
    """

    HOST = "0.0.0.0"  # TODO 这里变成可以配置的

    def __init__(self):
        self.loop = asyncio.get_event_loop()

        # {"port":{"tcp":tcp_server,"udp":udp_server}}
        self.__running_servers__ = defaultdict(dict)

    def get_server_by_port(self, port):
        return self.__running_servers__.get(port)

    async def init_server(self, user: User):

        running_server = self.get_server_by_port(user.port)
        if running_server:
            return

        tcp_server = await loop.create_server(LocalTCP(user.port), self.HOST, user.port)
        udp_server, _ = await loop.create_datagram_endpoint(
            LocalUDP(user.port), (self.HOST, user.port)
        )
        self.tcp_server = tcp_server
        self.udp_server = udp_server
        logging.info(
            "user:{} method:{} password:{} port:{} 已启动".format(
                user, user.method, user.password, user.port
            )
        )
