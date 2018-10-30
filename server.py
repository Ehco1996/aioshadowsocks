import os
import time
import logging
import asyncio

from config import TRANSFER_TYPE
from shadowsocks.server_pool import pool
from shadowsocks.user_tasks import UserTasks
from shadowsocks.logger import init_logger_config


def run_servers(transfer_type):
    # 初始化tansfer
    pool.init_transfer(transfer_type)

    # 启动定时任务
    user_tasks = UserTasks(pool)
    user_tasks.user_cron_task()

    loop = asyncio.get_event_loop()
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
