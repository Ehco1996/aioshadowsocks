import asyncio
import logging
import os
import signal

from shadowsocks.mdb.models import User
from shadowsocks.utils import (
    init_logger_config,
    init_memory_db,
    start_ss_cron_job,
    start_grpc_server,
)


def main(sync_time, use_json):
    def shutdown():
        User.shutdown_user_servers()
        loop.stop()

    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGTERM, shutdown)
    loop.create_task(start_grpc_server(loop))
    start_ss_cron_job(sync_time, use_json)

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        logging.info("正在关闭所有ss server")
        shutdown()


if __name__ == "__main__":
    use_json = False if os.getenv("SS_API_ENDPOINT") else True
    sync_time = int(os.getenv("SS_SYNC_TIME", 60))
    log_level = os.getenv("SS_LOG_LEVEL", "info")

    init_logger_config(log_level=log_level)
    init_memory_db()
    main(sync_time, use_json)
