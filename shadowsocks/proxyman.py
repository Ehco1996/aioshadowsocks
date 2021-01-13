import asyncio
import logging
from collections import defaultdict

from shadowsocks.core import LocalTCP, LocalUDP
from shadowsocks.mdb.models import User


class ProxyMan:
    """
    1. 将model的调用都放在这里
    2. server相关的东西也放在这里
    app -> proxyman -> core ->cipherman/model
    """

    AEAD_METHOD_LIST = [
        "chacha20-ietf-poly1305",
        "aes-128-gcm",
        "aes-256-gcm",
    ]

    def __init__(self, listen_host):
        self.loop = asyncio.get_event_loop()

        # {"port":{"tcp":tcp_server,"udp":udp_server}}
        self.__running_servers__ = defaultdict(dict)

        self.api_endpoint = None
        self.sync_time = None
        self.listen_host = listen_host

    def get_server_by_port(self, port):
        return self.__running_servers__.get(port)

    async def start_ss_server(self):
        for user in User.select().where(User.enable == True):
            try:
                await self.init_server(user)
            except Exception as e:
                logging.error(e)
                self.loop.stop()
        for user in User.select().where(User.enable == False):
            self.close_user_server(user)

    async def init_server(self, user: User):

        running_server = self.get_server_by_port(user.port)
        if running_server:
            return

        tcp_server = await self.loop.create_server(
            LocalTCP(user.port), self.listen_host, user.port, reuse_port=True
        )
        udp_server, _ = await self.loop.create_datagram_endpoint(
            LocalUDP(user.port), (self.listen_host, user.port), reuse_port=True
        )
        self.__running_servers__[user.port] = {
            "tcp": tcp_server,
            "udp": udp_server,
        }
        logging.info(
            "user:{} method:{} password:{} {}:{} 已启动".format(
                user, user.method, user.password, self.listen_host, user.port
            )
        )

    def close_user_server(self, user):
        running_server = self.get_server_by_port(user.port)
        if running_server and user.method not in self.AEAD_METHOD_LIST:
            running_server["tcp"].close()
            running_server["udp"].close()
            self.__running_servers__.pop(user.port)
            logging.info(f"user {user} 已关闭!")

    def close_server(self):
        for port, server_data in self.__running_servers__.items():
            server_data["tcp"].close()
            server_data["udp"].close()
            logging.info(f"port:{port} 已关闭!")
