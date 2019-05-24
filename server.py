import asyncio
import logging

from shadowsocks.cron import main_cron_job
from shadowsocks.utils import init_logger_config, init_memory_db


def run_servers():

    loop = asyncio.get_event_loop()

    try:
        # 定时任务
        main_cron_job()
        loop.run_forever()
    except KeyboardInterrupt:
        logging.info("正在关闭所有ss server")
        loop.stop()


if __name__ == "__main__":
    init_logger_config(log_level="info")
    init_memory_db()
    run_servers()
