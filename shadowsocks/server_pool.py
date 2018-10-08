import os
import time
import logging
import asyncio

from transfer.web_transfer import WebTransfer
from transfer.json_transfer import JsonTransfer


class ServerPool:
    _instance = None

    transfer = None

    # {'user_id': {
    #     'user': '<user instance>',
    #     'tcp': 'tcp_local_handler',
    #     'udp': 'udp_local_handler'}
    #  }
    local_handlers = {}
    balck_user_list = []

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
        return cls.local_handlers[user_id]['user']

    @classmethod
    def get_user_list(cls):
        user_list = []
        for user_id in cls.local_handlers.keys():
            user_list.append(cls.get_user_by_id(user_id))
        return user_list

    @classmethod
    def check_user_exist(cls, user_id):
        return user_id in cls.local_handlers.keys()

    @classmethod
    def _init_user(cls, user):
        cls.local_handlers[user.user_id] = {
            'user': user, 'tcp': None, 'udp': None}

    @classmethod
    def remove_user(cls, user_id):
        user_data = cls.local_handlers.pop(user_id)
        user_data['tcp'].close()
        user_data['udp'].close()

    @classmethod
    def check_user_traffic(cls, user_list):
        '''删除超出流量的用户'''
        for user in user_list:
            if user.used_traffic > user.total_traffic:
                cls.remove_user(user.user_id)
                logging.warning('user_id {} out of traffic used:{}'.format(
                    user.user_id, user.human_used_traffic))
        logging.info('checked user traffic')

    @classmethod
    def check_user_limit(cls, user_list):
        '''user rate limit'''
        pass

    @classmethod
    def async_user(cls):
        '''
        每隔60s检查一次是否有新user
        '''
        try:
            # post user traffic to server
            user_list = cls.get_user_list()
            cls.transfer.update_all_user(user_list)
            now = int(time.time())
            logging.info(
                'async user config cronjob current time {}'.format(now))
            # user rate limit
            cls.check_user_limit(user_list)
            # del out of traffic user from pool
            cls.check_user_traffic(user_list)
            # create task
            loop = asyncio.get_event_loop()
            coro = cls.async_user_config()
            loop.create_task(coro)
        except Exception as e:
            logging.warning('async_user error {}'.format(e))
        # crontab job for every 60s
        loop.call_later(60, cls.async_user)

    @classmethod
    async def async_user_config(cls):
        '''
        同步用户配置
        创建local连接
        加入事件循环
        '''
        from shadowsocks.udpreply import LocalUDP
        from shadowsocks.tcpreply import LocalTCP

        configs = cls.transfer.get_all_user_configs()
        if not configs:
            logging.error('get user config faild')
            return
        loop = asyncio.get_event_loop()
        local_address = configs['local_address']

        for user in configs['users']:
            user_id = user.user_id
            # 去除黑名单里的用户
            if user_id in cls.balck_user_list:
                continue

            if cls.check_user_exist(user_id) is False:
                logging.info("user_id:{} pass:{} 在 {} 的 {} 端口启动啦！".format(
                    user_id, user.password, local_address, user.port))

                # init user in server pool
                cls._init_user(user)

                # TCP sevcer
                tcp_server = loop.create_server(
                    LocalTCP(user.user_id), local_address, user.port)
                asyncio.ensure_future(tcp_server)
                cls.local_handlers[user.user_id]['tcp'] = tcp_server

                # UDP server
                udp_server = loop.create_datagram_endpoint(
                    LocalUDP(user.user_id), (local_address, user.port))
                asyncio.ensure_future(udp_server)
                cls.local_handlers[user.user_id]['udp'] = udp_server

            else:
                # update user config with db/server
                current_user = cls.get_user_by_id(user.user_id)
                current_user.total = user.total_traffic
                current_user.upload_traffic = user.upload_traffic
                current_user.download_traffic = user.upload_traffic
