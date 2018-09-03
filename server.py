import os
import logging
import asyncio

from shadowsocks.server_pool import ServerPool
from shadowsocks.logger import init_logger_config


def run_servers(transfer_type):

    async def async_user_task(pool):
        pool.async_user()

    loop = asyncio.get_event_loop()
    pool = ServerPool()

    pool.init_transfer(transfer_type)

    # 启动定时任务
    asyncio.ensure_future(async_user_task(pool))

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        logging.info('正在关闭所有ss server')
        for data in pool.user_handlers.values():
            user = data['user']
            servers = data['handlers']
            logging.info('正在关闭user_id: {} 的连接'.format(user.user_id))
            for server in servers:
                server.close()

        loop.stop()


if __name__ == "__main__":
    from config import TRANSFER_TYPE
    init_logger_config(log_level="info")
    run_servers(TRANSFER_TYPE)
