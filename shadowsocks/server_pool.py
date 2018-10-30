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
    def init_transfer(cls, transfer_type):
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
    def filter_black_user_list(cls):
        now = int(time.time())
        need_release_ids = []
        for user_id in cls.balck_user_ids:
            user = cls.get_user_by_id(user_id)
            if user.status == 1 and (now-user.jail_time) > c.RELEASE_TIME:
                need_release_ids.append(user_id)
                user.status = 0
                logging.warning(
                    'release user: {} from  black_list'.format(user_id))
        # release user
        for user_id in need_release_ids:
            cls.balck_user_ids.remove(user_id)

    @classmethod
    def filter_user(cls, user):
        if not user:
            return False
        elif user.user_id in cls.balck_user_ids:
            return False
        elif user.tcp_count > c.MAX_TCP_CONNECT:
            return False
        return True

    @classmethod
    def add_user_to_jail(cls, user_id):
        now = int(time.time())
        cls.balck_user_ids.add(user_id)
        user = cls.get_user_by_id(user_id)
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


pool = ServerPool()
