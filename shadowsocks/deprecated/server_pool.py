import os
import time
import logging
import asyncio

import config as c
from transfer.web_transfer import WebTransfer
from transfer.json_transfer import JsonTransfer
from shadowsocks.user_pool import UserPool


class ServerPool:
    _instance = None

    transfer = None
    user_pool = None

    # {user_id: {
    #     'tcp': 'tcp_local_handler',
    #     'udp': 'udp_local_handler'}
    #  }
    USER_SERVER_MAP = {}

    # {port: {
    #     'tcp': 'tcp_local_handler',
    #     'udp': 'udp_local_handler'}
    #  }
    ONE_PORT_SERVERS = {}

    def __new__(cls, *args, **kw):
        if not cls._instance:
            cls._instance = super(ServerPool, cls).__new__(cls, *args, **kw)
            # init user_pool
            cls.user_pool = UserPool()
            # init transfer
            if c.TRANSFER_TYPE == "webapi":
                cls.transfer = WebTransfer(c.TOKEN, c.WEBAPI_URL, c.NODE_ID)
            else:
                path = os.path.join(os.getcwd(), "defaultconfig.json").encode()
                cls.transfer = JsonTransfer(path)

        return cls._instance

    @classmethod
    def check_user_exist(cls, user):
        return user.user_id in cls.user_pool.USER_MAP

    @classmethod
    async def _init_user_server(cls, loop, user):
        from shadowsocks.tcpreply import LocalTCP
        from shadowsocks.udpreply import LocalUDP

        # TCP server
        tcp_server = await loop.create_server(LocalTCP(user), c.LOCAL_ADDRES, user.port)
        # UDP server
        udp_server, _ = await loop.create_datagram_endpoint(
            LocalUDP(user), (c.LOCAL_ADDRES, user.port)
        )
        cls.USER_SERVER_MAP[user.user_id] = {"tcp": tcp_server, "udp": udp_server}
        cls.user_pool.add_user(user)
        logging.info(
            f"user:{user} pass:{user.password} 在 {c.LOCAL_ADDRES} 的 {user.port} 端口启动啦"
        )

    @classmethod
    async def _init_one_port_server(cls, loop, user):
        from shadowsocks.tcpreply import LocalTCP
        from shadowsocks.udpreply import LocalUDP

        if user.port not in cls.ONE_PORT_SERVERS:
            cls.ONE_PORT_SERVERS[user.port] = {"tcp": None, "udp": None}
            # TCP server
            tcp_server = await loop.create_server(
                LocalTCP(user), c.LOCAL_ADDRES, user.port
            )
            # UDP server
            udp_server, _ = await loop.create_datagram_endpoint(
                LocalUDP(user), (c.LOCAL_ADDRES, user.port)
            )
            cls.ONE_PORT_SERVERS[user.port]["tcp"] = tcp_server
            cls.ONE_PORT_SERVERS[user.port]["udp"] = udp_server
        cls.user_pool.add_user(user)
        logging.info(
            f"user:{user} pass:{user.password} 在 {c.LOCAL_ADDRES} 的 {user.port} 端口启动啦"
        )

    @classmethod
    def _init_or_update_user_server(cls, loop):
        user_configs = cls.transfer.get_all_user_configs()
        if not user_configs:
            logging.error("get user config failed")
            return
        for user in user_configs:
            # TODO 更换port的情况还没考虑
            if not cls.check_user_exist(user):
                if user.node_type == user.NODE_TYPE_MUL_PORT:
                    loop.create_task(cls._init_user_server(loop, user))
                elif user.node_type == user.NODE_TYPE_ONE_PORT:
                    loop.create_task(cls._init_one_port_server(loop, user))
            else:
                # update user config with db/server
                current_user = cls.user_pool.get_by_user_id(user.user_id)
                current_user.password = user.password
                current_user.total = user.total_traffic
                current_user.upload_traffic = user.upload_traffic
                current_user.download_traffic = user.download_traffic

    @classmethod
    def sync_user_config_task(cls):
        loop = asyncio.get_event_loop()
        try:
            # post user traffic to server
            user_list = cls.user_pool.get_user_list()
            cls.transfer.update_all_user(user_list)
            logging.info(f"async user config cronjob current time {time.time()}")
            # clean not valid user
            cls.clean_not_valid_user()
            # check/init user server
            cls._init_or_update_user_server(loop)
        except Exception as e:
            logging.warning(f"async_user error {e}")
        # crontab job
        loop.call_later(c.SYNC_TIME, cls.sync_user_config_task)

    @classmethod
    def close_by_user_id(cls, user_id):
        if user_id in cls.USER_SERVER_MAP:
            user_servers = cls.USER_SERVER_MAP.pop(user_id)
            user_servers["tcp"].close()
            user_servers["udp"].close()
        cls.user_pool.remove_user_by_user_id(user_id)

    @classmethod
    def close_one_port_servers(cls):
        for port, servers in cls.ONE_PORT_SERVERS.items():
            servers["tcp"].close()
            servers["udp"].close()
            logging.info(f"运行在的{port}的单端口server已被关闭")

    @classmethod
    def clean_not_valid_user(cls):
        for user in cls.user_pool.get_user_list():
            if user.used_traffic > user.total_traffic:
                cls.close_by_user_id(user.user_id)
                logging.warning(
                    f"user {user} out of traffic used:{user.human_used_traffic}"
                )
            elif user.tcp_count > c.MAX_TCP_CONNECT or user.enable is False:
                cls.close_by_user_id(user.user_id)
                logging.warning(f"user: {user} not valid")


pool = ServerPool()
