import os
import logging
import asyncio

from shadowsocks.udpreply import LoaclUDP
from shadowsocks.tcpreply import LocalTCP
from shadowsocks.logger import init_logger_config
from shadowsocks.config_reader.json_reader import json_config_reader


def run_servers():
    init_logger_config(log_level="debug")

    path = os.path.join(os.getcwd(), 'defualtconfig.json').encode()
    configs = json_config_reader(path)
    local_adress = configs['local_adress']

    tcp_servers = []
    # udp_servers = []
    loop = asyncio.get_event_loop()

    for user in configs['users']:
        logging.info("user_id: {} password: {} 在 {} 的 {} 端口启动啦！".format(
            user.user_id, user.password, local_adress, user.port))

        # TCP sevcer
        tcp_server = loop.run_until_complete(
            loop.create_server(lambda: LocalTCP(
                user.method, user.password), local_adress, user.port))
        tcp_servers.append(tcp_server)

        # TODO UDP server

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        logging.info('正在关闭所有ss server')
        # TODO graceful shutdonw
        loop.stop()


if __name__ == "__main__":
    run_servers()
