import os
import time
import logging
import asyncio

from config import TRANSFER_TYPE
from shadowsocks.server_pool import pool
from shadowsocks.udpreply import LocalUDP
from shadowsocks.tcpreply import LocalTCP
from shadowsocks.logger import init_logger_config


def user_cron_task(pool):
    '''
    每隔60s检查一次是否有新user
    '''
    loop = asyncio.get_event_loop()
    try:
        # post user traffic to server
        user_list = pool.get_user_list()
        pool.transfer.update_all_user(user_list)
        now = int(time.time())
        logging.info(
            'async user config cronjob current time {}'.format(now))
        # filter user
        pool.filter_black_user_list()
        # del out of traffic user from pool
        pool.check_user_traffic(user_list)
        # create task
        loop.create_task(sync_user_config_task(pool))
    except Exception as e:
        logging.warning('async_user error {}'.format(e))
    # crontab job for every 60s
    loop.call_later(60, user_cron_task, pool)


async def sync_user_config_task(pool):
    configs = pool.transfer.get_all_user_configs()
    if not configs:
        logging.error('get user config faild')
        return
    loop = asyncio.get_event_loop()
    local_address = configs['local_address']
    for user in configs['users']:
        user_id = user.user_id
        # 跳过黑名单里的用户
        if user_id in pool.balck_user_ids:
            continue

        if pool.check_user_exist(user_id) is False:
            logging.info("user_id:{} pass:{} 在 {} 的 {} 端口启动啦！".format(
                user_id, user.password, local_address, user.port))

            # init user in server pool
            pool._init_user(user)

            # TCP sevcer
            tcp_server = loop.create_server(
                LocalTCP(user), local_address, user.port)
            asyncio.ensure_future(tcp_server)
            pool.local_handlers[user.user_id]['tcp'] = tcp_server

            # UDP server
            udp_server = loop.create_datagram_endpoint(
                LocalUDP(user), (local_address, user.port))
            asyncio.ensure_future(udp_server)
            pool.local_handlers[user.user_id]['udp'] = udp_server

        else:
            # update user config with db/server
            current_user = pool.get_user_by_id(user.user_id)
            current_user.total = user.total_traffic
            current_user.upload_traffic = user.upload_traffic
            current_user.download_traffic = user.download_traffic


def run_servers(transfer_type):
    loop = asyncio.get_event_loop()
    pool.init_transfer(transfer_type)

    # 启动定时任务
    user_cron_task(pool)

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        logging.info('正在关闭所有ss server')
        for user in pool.get_user_list():
            pool.remove_user(user.user_id)
        loop.stop()


if __name__ == "__main__":
    init_logger_config(log_level="info")
    run_servers(TRANSFER_TYPE)
