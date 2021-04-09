import asyncio
import json
import logging
from collections import defaultdict

import httpx

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

    def __init__(self, use_json, sync_time, listen_host, api_endpoint):
        self.use_json = use_json
        self.sync_time = sync_time
        self.listen_host = listen_host
        self.api_endpoint = api_endpoint
        self.loop = asyncio.get_event_loop()
        # NOTE {"port":{"tcp":tcp_server,"udp":udp_server}}
        self.__running_servers__ = defaultdict(dict)

    @staticmethod
    def create_or_update_from_json(path):
        with open(path, "r") as f:
            data = json.load(f)
            User.create_or_update_by_user_data_list(data["users"])

    @staticmethod
    async def get_user_from_remote(url):
        async with httpx.AsyncClient() as client:
            res = await client.get(url)
            User.create_or_update_by_user_data_list(res.json()["users"])

    @staticmethod
    async def flush_metrics_to_remote(url):
        data = [
            {
                "user_id": user.user_id,
                "ip_list": list(user.ip_list),
                "tcp_conn_num": user.tcp_conn_num,
                "upload_traffic": user.upload_traffic,
                "download_traffic": user.download_traffic,
            }
            for user in User.get_and_reset_need_sync_user_metrics()
        ]
        async with httpx.AsyncClient() as client:
            await client.post(url, json={"data": data})

    async def sync_from_remote_cron(self):
        await self.flush_metrics_to_remote(self.api_endpoint)
        await self.get_user_from_remote(self.api_endpoint)

    async def sync_from_json_cron(self):
        self.create_or_update_from_json("userconfigs.json")

    def get_server_by_port(self, port):
        return self.__running_servers__.get(port)

    async def start_and_check_ss_server(self):
        """
        启动ss server并且定期检查是否要开启新的server
        TODO 关闭不需要的server
        """

        if self.use_json:
            await self.sync_from_json_cron()
        else:
            await self.sync_from_remote_cron()

        for user in User.select().where(User.enable == True):
            try:
                await self.init_server(user)
            except Exception as e:
                logging.error(e)
                self.loop.stop()
        self.loop.call_later(
            self.sync_time,
            self.loop.create_task,
            self.start_and_check_ss_server(),
        )

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

    def close_server(self):
        for port, server_data in self.__running_servers__.items():
            server_data["tcp"].close()
            server_data["udp"].close()
            logging.info(f"port:{port} 已关闭!")
