import asyncio
import logging

from collections import defaultdict

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

    async def start_ss_json_server(self):
        User.create_or_update_from_json("userconfigs.json")
        for user in User.select():
            await self.loop.create_task(self.init_server(user))

    async def start_remote_sync_server(self, api_endpoint, sync_time):
        try:
            User.create_or_update_from_remote(api_endpoint)
            # TODO 用户流量记录
            # UserServer.flush_metrics_to_remote(api_endpoint)
            for user in User.select():
                await self.loop.create_task(self.init_server(user))
        except Exception as e:
            logging.warning(f"sync user error {e}")
        self.loop.call_later(
            sync_time, self.start_remote_sync_server, api_endpoint, sync_time
        )

    async def init_server(self, user: User):

        running_server = self.get_server_by_port(user.port)
        if running_server:
            logging.info(
                "user:{} method:{} password:{} 共享端口:{}".format(
                    user, user.method, user.password, user.port
                )
            )
            return

        tcp_server = await self.loop.create_server(
            LocalTCP(user.port), self.HOST, user.port
        )
        udp_server, _ = await self.loop.create_datagram_endpoint(
            LocalUDP(user.port), (self.HOST, user.port)
        )
        self.__running_servers__[user.port] = {
            "tcp": tcp_server,
            "udp": udp_server,
        }
        logging.info(
            "user:{} method:{} password:{} port:{} 已启动".format(
                user, user.method, user.password, user.port
            )
        )

    def close_server(self):
        for port, server_data in self.__running_servers__.items():
            server_data["tcp"].close()
            server_data["udp"].close()
            logging.info(f"port:{port} 已关闭!")
