import asyncio
import logging

from shadowsocks.mdb.models import User


def main_cron_job():
    try:
        User.create_or_update_from_remote()
        User.init_user_servers()
    except Exception as e:
        logging.warning(f"sync user error {e}")

    # crontab job
    loop = asyncio.get_event_loop()
    loop.call_later(100000, main_cron_job)
