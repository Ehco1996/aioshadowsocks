import os
import logging
import asyncio

from shadowsocks.udpreply import LoaclUDP
from shadowsocks.tcpreply import LocalTCP
from shadowsocks.logger import init_logger_config
from shadowsocks.config_reader.json_reader import json_config_reader


async def run_servers(configs):

    tcp_servers = []
    udp_transports = []
    loop = asyncio.get_event_loop()
    local_adress = configs['local_adress']

    for user in configs['users']:
        logging.info("user_id: {} password: {} 在 {} 的 {} 端口启动啦！".format(
            user.user_id, user.password, local_adress, user.port))

        # TCP sevcer
        tcp_server = loop.run_until_complete(
            loop.create_server(lambda: LocalTCP(
                user.method, user.password), local_adress, user.port))
        tcp_servers.append(tcp_server)

        # UDP server
        listen = loop.create_datagram_endpoint(lambda: LoaclUDP(
            user.method, user.password), (local_adress, user.port))
        udp_transport, _ = loop.run_until_complete(listen)
        udp_transports.append(udp_transport)

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        logging.info('正在关闭所有ss server')

        for tcp_server in tcp_servers:
            tcp_server.close()
            loop.run_until_complete(tcp_server.wait_closed())
        for udp_transport in udp_transports:
            udp_transport.close()
    finally:
        loop.stop()


if __name__ == "__main__":
    init_logger_config(log_level="info")
    path = os.path.join(os.getcwd(), 'defualtconfig.json').encode()
    run_servers(json_config_reader(path))
