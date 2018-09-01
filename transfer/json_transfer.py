import os
import logging

from transfer.users import User
from transfer.utils import json_config_reader


class JsonTransfer:
    def __init__(self, path):
        self.path = path
        self.transfer_mul = 1.0
        self.local_address = '0.0.0.0'

    def get_all_user_configs(self):
        '''
        拉取符合要求的用户信息
        '''

        # 获取节点流量比例信息
        data = json_config_reader(self.path)
        # 记录流量比例
        self.transfer_mul = data['transfer_mul']
        # 记录local_address
        self.local_address = data['local_address']
        # 获取符合条件的用户信息
        if not data['users']:
            logging.warning('没有查询到满足要求的user，请检查自己的config')
            return
        return data

    def update_all_user(self, user_list):
        '''
        更新user信息，上报用户流量
        '''
        data = []
        for user in user_list:
            data.append({
                'user_id': user.user_id,
                'u': user.once_used_u * self.transfer_mul,
                'd': user.once_used_d * self.transfer_mul
            })
            # reset user used traffic
            user.once_used_u = 0
            user.once_used_d = 0
        print(data)
