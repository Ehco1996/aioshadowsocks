import os
import time
import logging
import asyncio

import config as c
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
    balck_user_ids = set()

    def __new__(cls, *args, **kw):
        if not cls._instance:
            cls._instance = super(ServerPool, cls).__new__(cls, *args, **kw)
        return cls._instance

    @classmethod
    def _get_user_by_id(cls, user_id):
        return cls.local_handlers[user_id]['user']

    @classmethod
    def _check_user_exist(cls, user_id, port):
        if user_id in cls.local_handlers:
            current_user = cls._get_user_by_id(user_id)
            # change user port
            if current_user.port != port:
                pool.remove_user(user_id)
                return False
            return True
        else:
            return False

    @classmethod
    async def _init_user_server(cls, loop, user):
        from shadowsocks.udpreply import LocalUDP
        from shadowsocks.tcpreply import LocalTCP
        # TCP sevcer
        tcp_server = await loop.create_server(
            LocalTCP(user), c.LOACL_ADREES, user.port)
        # UDP server
        udp_server, _ = await loop.create_datagram_endpoint(
            LocalUDP(user), (c.LOACL_ADREES, user.port))
        cls.local_handlers[user.user_id] = {
            'user': user, 'tcp': tcp_server, 'udp': udp_server}
        logging.info("user_id:{} pass:{} 在 {} 的 {} 端口启动啦！".format(
            user.user_id, user.password,  c.LOACL_ADREES, user.port))

    @classmethod
    def _init_or_update_user_server(cls, loop):
        configs = cls.transfer.get_all_user_configs()
        if not configs:
            logging.error('get user config faild')
            return
        for user in configs['users']:
            # 跳过黑名单里的用户
            if user.user_id in cls.balck_user_ids:
                continue
            if not cls._check_user_exist(user.user_id, user.port):
                loop.create_task(cls._init_user_server(loop, user))
            else:
                # update user config with db/server
                current_user = cls._get_user_by_id(user.user_id)
                current_user.password = user.password
                current_user.total = user.total_traffic
                current_user.upload_traffic = user.upload_traffic
                current_user.download_traffic = user.download_traffic

    @classmethod
    def _check_user_traffic(cls, user_list):
        '''删除超出流量的用户'''
        for user in user_list:
            if user.used_traffic > user.total_traffic:
                cls.remove_user(user.user_id)
                logging.warning('user_id {} out of traffic used:{}'.format(
                    user.user_id, user.human_used_traffic))
        logging.info('checked user traffic')

    @classmethod
    def _add_user_to_jail(cls, user_id):
        now = int(time.time())
        cls.balck_user_ids.add(user_id)
        user = cls._get_user_by_id(user_id)
        if user.status == 0:
            user_data = cls.local_handlers[user_id]
            user_data['tcp'].close()
            user_data['udp'].close()
            user.status = 1
            user.jail_time = now
            logging.warning(
                'close user: {} connection & addto black_list'.format(user_id))
        else:
            logging.warning(
                'user: {} already in black_list'.format(user_id))

    @classmethod
    def _release_black_user(cls):
        now = int(time.time())
        need_release_ids = []
        for user_id in cls.balck_user_ids:
            user = cls._get_user_by_id(user_id)
            if user.status == 1 and (now-user.jail_time) > c.RELEASE_TIME:
                need_release_ids.append(user_id)
                user.status = 0
                logging.warning(
                    'release user: {} from  black_list'.format(user_id))
        # release user
        for user_id in need_release_ids:
            cls.balck_user_ids.remove(user_id)

    @classmethod
    def get_user_list(cls):
        user_list = []
        for user_id in cls.local_handlers.keys():
            user_list.append(cls._get_user_by_id(user_id))
        return user_list

    @classmethod
    def init_transfer(cls, transfer_type):
        if transfer_type == 'webapi':
            cls.transfer = WebTransfer(c.TOKEN, c.WEBAPI_URL, c.NODE_ID)
        else:
            path = os.path.join(os.getcwd(), 'defualtconfig.json').encode()
            cls.transfer = JsonTransfer(path)

    @classmethod
    def sync_user_config_task(cls):
        loop = asyncio.get_event_loop()
        try:
            # post user traffic to server
            user_list = cls.get_user_list()
            cls.transfer.update_all_user(user_list)
            now = int(time.time())
            logging.info(
                'async user config cronjob current time {}'.format(now))
            cls._release_black_user()
            # del out of traffic user from pool
            cls._check_user_traffic(user_list)
            # check/init user server
            cls._init_or_update_user_server(loop)
        except Exception as e:
            logging.warning('async_user error {}'.format(e))
        # crontab job
        loop.call_later(c.SYNC_TIME, cls.sync_user_config_task)

    @classmethod
    def filter_user(cls, user):
        if not user:
            return False
        elif user.user_id in cls.balck_user_ids:
            return False
        elif user.tcp_count > c.MAX_TCP_CONNECT:
            return False
        elif user.enable is False:
            return False
        return True

    @classmethod
    def remove_user(cls, user_id):
        user_servers = cls.local_handlers.pop(user_id)
        user_servers['tcp'].close()
        user_servers['udp'].close()


pool = ServerPool()
