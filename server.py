import os
import logging
import asyncio

from shadowsocks.server_pool import ServerPool
from shadowsocks.logger import init_logger_config
from shadowsocks.config_reader.json_reader import json_config_reader


def run_servers(configs):

    async def async_user_task(pool):
        pool.async_user()

    loop = asyncio.get_event_loop()
    pool = ServerPool()

    asyncio.ensure_future(pool.async_user_config(configs))
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
    init_logger_config(log_level="info")
    path = os.path.join(os.getcwd(), 'defualtconfig.json').encode()
    run_servers(json_config_reader(path))
