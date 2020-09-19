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

    async def sync_from_remote(self):
        try:
            User.flush_metrics_to_remote(self.api_endpoint)
            User.create_or_update_from_remote(self.api_endpoint)
        except Exception as e:
            logging.warning(f"sync user error {e}")
        for user in User.select().where(User.enable == True):
            await self.loop.create_task(self.init_server(user))
        for user in User.select().where(User.enable == False):
            self.close_user_server(user)
        self.loop.call_later(
            self.sync_time, self.loop.create_task, self.sync_from_remote()
        )

    async def start_ss_json_server(self):
        User.create_or_update_from_json("userconfigs.json")
        for user in User.select().where(User.enable == True):
            await self.loop.create_task(self.init_server(user))

    async def start_remote_sync_server(self, api_endpoint, sync_time):
        self.api_endpoint = api_endpoint
        self.sync_time = sync_time
        await self.sync_from_remote()

    async def init_server(self, user: User):

        running_server = self.get_server_by_port(user.port)
        if running_server:
            return

        tcp_server = await self.loop.create_server(
            LocalTCP(user.port), self.listen_host, user.port
        )
        udp_server, _ = await self.loop.create_datagram_endpoint(
            LocalUDP(user.port), (self.listen_host, user.port)
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
