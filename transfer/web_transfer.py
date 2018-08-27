import logging

from transfer.users import User
from transfer.utils import EhcoApi


class WebTransfer:
    def __init__(self, token, url, node_id, local_address):
        self.api = EhcoApi(token, url)
        self.local_address = local_address
        self.node_id = node_id
        self.transfer_mul = 1.0

    def get_all_user_configs(self):
        '''
        拉取符合要求的用户信息
        '''

        node_id = self.node_id

        # 获取节点流量比例信息
        nodeinfo = self.api.getApi('/nodes/{}'.format(node_id))
        if not nodeinfo:
            logging.warning('没有查询到满足要求的节点，请检查自己的node_id!'
                            '当前节点ID: {}'.format(node_id))
            return
        logging.info('节点id: {} 流量比例: {}'.format(node_id, nodeinfo[0]))
        # 记录流量比例
        self.transfer_mul = float(nodeinfo[0])

        # 获取符合条件的用户信息
        data = self.api.getApi('/users/nodes/{}'.format(node_id))
        if not data:
            logging.warning('没有查询到满足要求的user，请检查自己的node_id!')
            return
        users = []
        for user_info in data:
            users.append(User(**user_info))
        configs = {'local_address': self.local_address, 'users': users}
        return configs

    def update_all_user(self, user_list):
        pass

        # # 用户流量上报
        # data = []
        # for port in dt_transfer.keys():
        #     if (port not in dt_transfer.keys()) or (port not in self.port_uid_table.keys()):
        #         continue
        #     elif dt_transfer[port][0] == 0 and dt_transfer[port][1] == 0:
        #         continue
        #     data.append({'u': dt_transfer[port][0] * self.cfg['transfer_mul'],
        #                  'd': dt_transfer[port][1] * self.cfg['transfer_mul'],
        #                  'user_id': self.port_uid_table[port]})
        #     update_transfer[port] = dt_transfer[port]
        # if len(data) > 0:
        #     tarffic_data = {'node_id': node_id,
        #                     'data': data}
        #     webapi.postApi('/traffic/upload', tarffic_data)

        # # 节点人数上报
        # alive_user_count = len(self.onlineuser_cache)
        # online_data = {'node_id': node_id,
        #                'online_user': alive_user_count}
        # webapi.postApi('/nodes/online', online_data)

        # return update_transfer
