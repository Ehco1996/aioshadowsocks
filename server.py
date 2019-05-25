import asyncio
import logging

from shadowsocks.mdb.models import User
from shadowsocks.utils import init_logger_config, init_memory_db


def cron_task():
    loop = asyncio.get_event_loop()
    try:
        User.create_or_update_from_json("defaultconfig.json")
        User.init_user_servers()
    except Exception as e:
        logging.warning(f"sync user error {e}")
    # crontab job 60/s
    loop.call_later(60, cron_task)


def run_servers():
    loop = asyncio.get_event_loop()
    try:
        cron_task()
        loop.run_forever()
    except KeyboardInterrupt:
        logging.info("正在关闭所有ss server")
        loop.stop()


if __name__ == "__main__":
    init_logger_config(log_level="info")
    init_memory_db()
    run_servers()
