import os
import time
import logging
import asyncio

from transfer.web_transfer import WebTransfer
from transfer.json_transfer import JsonTransfer


class ServerPool:
    _instance = None

    transfer = None

    user_ids = list()
    tcp_server_ids = list()
    udp_server_ids = list()

    # {'user_id':{
    #              'user':<user instance>,
    #              'handlers:[<local handler>,]')}
    user_handlers = {}

    def __new__(cls, *args, **kw):
        if not cls._instance:
            cls._instance = super(ServerPool, cls).__new__(cls, *args, **kw)
        return cls._instance

    @classmethod
    def init_transfer(cls, transfer_type):
        import config as c
        if transfer_type == 'webapi':
            cls.transfer = WebTransfer(
                c.TOKEN, c.WEBAPI_URL, c.NODE_ID, c.LOACL_ADREES)
        else:
            path = os.path.join(os.getcwd(), 'defualtconfig.json').encode()
            cls.transfer = JsonTransfer(path)

    @classmethod
    def get_user_by_id(cls, user_id):
        return cls.user_handlers[user_id]['user']

    @classmethod
    def get_user_list(cls):
        user_list = []
        for user_id in cls.user_ids:
            user_list.append(cls.get_user_by_id(user_id))
        return user_list

    @classmethod
    def _check_user_exist(cls, user_id):
        return user_id in cls.user_ids

    @classmethod
    def _init_user(cls, user):
        cls.user_ids.append(user.user_id)
        cls.user_handlers[user.user_id] = {'user': user, 'handlers': list()}

    @classmethod
    def check_tcp_server(cls, server_id):
        return server_id in cls.tcp_server_ids

    @classmethod
    def check_udp_server(cls, server_id):
        return server_id in cls.udp_server_ids

    @classmethod
    def add_tcp_server(cls, server_id, user, server_instance):
        cls.tcp_server_ids.append(server_id)
        cls.user_handlers[user.user_id]['handlers'].append(server_instance)

    @classmethod
    def add_udp_server(cls, server_id, user, server_instance):
        cls.udp_server_ids.append(server_id)
        cls.user_handlers[user.user_id]['handlers'].append(server_instance)

    @classmethod
    def async_user(cls):
        '''每隔60s检查一次是否有新user'''

        # post user traffic to server
        cls.transfer.update_all_user(cls.get_user_list())
        loop = asyncio.get_event_loop()
        now = int(time.time())
        # create task
        coro = cls.async_user_config()
        loop.create_task(coro)
        logging.info('async user config cronjob current time {}'.format(now))
        # crontab job for every 60s
        loop.call_later(60, cls.async_user)

    @classmethod
    async def async_user_config(cls):
        '''
        同步用户配置
        创建local连接
        加入事件循环
        '''
        from shadowsocks.udpreply import LoaclUDP
        from shadowsocks.tcpreply import LocalTCP

        configs = cls.transfer.get_all_user_configs()
        if not configs:
            logging.error('get user config faild')
            return
        loop = asyncio.get_event_loop()
        local_address = configs['local_address']

        for user in configs['users']:
            if cls._check_user_exist(user.user_id) is False:
                logging.info("user_id:{} pass:{} 在 {} 的 {} 端口启动啦！".format(
                    user.user_id, user.password, local_address, user.port))

                # TCP sevcer
                tcp_server = loop.create_server(
                    LocalTCP(user), local_address, user.port)
                asyncio.ensure_future(tcp_server)

                # UDP server
                udp_server = loop.create_datagram_endpoint(
                    LoaclUDP(user), (local_address, user.port))
                asyncio.ensure_future(udp_server)

                # init user in server pool
                cls._init_user(user)
            else:
                logging.info(
                    'update user  user_id {}'.format(user.user_id))
                # update user config with db/server
                current_user = cls.get_user_by_id(user.user_id)
                current_user.total = user.total_traffic
                current_user.upload_traffic = user.upload_traffic
                current_user.download_traffic = user.upload_traffic
