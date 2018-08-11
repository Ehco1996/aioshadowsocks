import logging
import asyncio

from shadowsocks.udpreply import LoaclUDP
from shadowsocks.tcpreply import LocalTCP


async def async_user_config(configs):
    '''
    同步用户配置数据并加入事件循环
    '''
    tcp_servers = []
    udp_transports = []
    loop = asyncio.get_event_loop()
    local_adress = configs['local_adress']

    for user in configs['users']:

        logging.info("user_id: {} password: {} 在 {} 的 {} 端口启动啦！".format(
            user.user_id, user.password, local_adress, user.port))

        # TCP sevcer
        tcp_server = loop.create_server(lambda: LocalTCP(
            user.method, user.password, user), local_adress, user.port)
        asyncio.ensure_future(tcp_server)
        tcp_servers.append(tcp_server)

        # UDP server
        listen = loop.create_datagram_endpoint(lambda: LoaclUDP(
            user.method, user.password, user), (local_adress, user.port))
        udp_transport = asyncio.ensure_future(listen)
        udp_transports.append(udp_transport)

    return tcp_servers, udp_transports
