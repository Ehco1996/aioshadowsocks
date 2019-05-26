import os
import asyncio
import logging

from shadowsocks.mdb.models import User
from shadowsocks.utils import init_logger_config, init_memory_db


def cron_task(use_json=False):

    loop = asyncio.get_event_loop()
    try:
        if use_json:
            User.create_or_update_from_json("userconfigs.json")
        else:
            User.create_or_update_from_remote()
        User.flush_data_to_remote()
        User.init_user_servers()
    except Exception as e:
        logging.warning(f"sync user error {e}")
    # cron job 60/s
    loop.call_later(6, cron_task, use_json)


def run_servers():
    loop = asyncio.get_event_loop()
    use_json = False if os.getenv("API_ENDPOINT") else True
    try:
        cron_task(use_json)
        loop.run_forever()
    except KeyboardInterrupt:
        logging.info("正在关闭所有ss server")
        User.shutdown_user_servers()
        loop.stop()


if __name__ == "__main__":
    init_logger_config(log_level="info")
    init_memory_db()
    run_servers()
