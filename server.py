import logging
import asyncio

from shadowsocks.server_pool import pool
from shadowsocks.logger import init_logger_config


def run_servers():

    # 定时任务
    pool.sync_user_config_task()

    loop = asyncio.get_event_loop()
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        logging.info("正在关闭所有ss server")
        pool.close_one_port_servers()
        for user in pool.user_pool.get_user_list():
            pool.close_by_user_id(user.user_id)
        loop.stop()


if __name__ == "__main__":
    init_logger_config(log_level="info")
    run_servers()
