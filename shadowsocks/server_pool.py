import logging
import asyncio


class ServerPool:
    _instance = None

    tcp_server_ids = list()
    udp_server_ids = list()

    tcp_servers = {}
    udp_servers = {}

    def __new__(cls, *args, **kw):
        if not cls._instance:
            cls._instance = super(ServerPool, cls).__new__(cls, *args, **kw)
        return cls._instance

    @classmethod
    def add_tcp_server(cls, server_id, server_instance):
        cls.tcp_server_ids.append(server_id)
        cls.tcp_servers[server_id] = server_instance

    @classmethod
    def add_udp_server(cls, server_id, server_instance):
        cls.udp_server_ids.append(server_id)
        cls.udp_servers[server_id] = server_instance

    @classmethod
    def check_tcp_server(cls, server_id):
        return server_id in cls.tcp_server_ids

    @classmethod
    def check_udp_server(cls, server_id):
        return server_id in cls.udp_server_ids


async def async_user_config(configs):
    '''
    同步用户配置
    创建local连接
    加入事件循环
    '''
    from shadowsocks.udpreply import LoaclUDP
    from shadowsocks.tcpreply import LocalTCP

    loop = asyncio.get_event_loop()
    local_adress = configs['local_adress']

    for user in configs['users']:

        logging.info("user_id: {} password: {} 在 {} 的 {} 端口启动啦！".format(
            user.user_id, user.password, local_adress, user.port))

        # TCP sevcer
        tcp_server = loop.create_server(lambda: LocalTCP(
            user.method, user.password, user), local_adress, user.port)
        asyncio.ensure_future(tcp_server)

        # UDP server
        listen = loop.create_datagram_endpoint(lambda: LoaclUDP(
            user.method, user.password, user), (local_adress, user.port))
        asyncio.ensure_future(listen)
