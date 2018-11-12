import os
import time
import logging
import asyncio

from shadowsocks.udpreply import LocalUDP
from shadowsocks.tcpreply import LocalTCP
from shadowsocks.logger import init_logger_config


class UserTasks:

    def __init__(self, pool):
        self.pool = pool

    def user_cron_task(self):
        '''
        每隔60s检查一次是否有新user
        '''
        loop = asyncio.get_event_loop()
        try:
            # post user traffic to server
            user_list = self.pool.get_user_list()
            self.pool.transfer.update_all_user(user_list)
            now = int(time.time())
            logging.info(
                'async user config cronjob current time {}'.format(now))
            # filter user
            self.pool.filter_black_user_list()
            # del out of traffic user from pool
            self.pool.check_user_traffic(user_list)
            # create task
            loop.create_task(self.sync_user_config_task())
        except Exception as e:
            logging.warning('async_user error {}'.format(e))
        # crontab job for every 60s
        loop.call_later(60, self.user_cron_task)

    async def sync_user_config_task(self):
        configs = self.pool.transfer.get_all_user_configs()
        if not configs:
            logging.error('get user config faild')
            return
        loop = asyncio.get_event_loop()
        local_address = configs['local_address']
        for user in configs['users']:
            user_id = user.user_id
            port = user.port
            # 跳过黑名单里的用户
            if user_id in self.pool.balck_user_ids:
                continue
            if self.pool.check_user_exist(user_id, port) is False:
                logging.info("user_id:{} pass:{} 在 {} 的 {} 端口启动啦！".format(
                    user_id, user.password, local_address, user.port))
                # init user in server pool
                self.pool._init_user(user)
                # TCP sevcer
                tcp_server = await loop.create_server(
                    LocalTCP(user), local_address, user.port)
                self.pool.local_handlers[user.user_id]['tcp'] = tcp_server
                # UDP server
                udp_server, _ = await loop.create_datagram_endpoint(
                    LocalUDP(user), (local_address, user.port))
                self.pool.local_handlers[user.user_id]['udp'] = udp_server

            else:
                # update user config with db/server
                current_user = self.pool.get_user_by_id(user.user_id)
                current_user.password = user.password
                current_user.total = user.total_traffic
                current_user.upload_traffic = user.upload_traffic
                current_user.download_traffic = user.download_traffic
