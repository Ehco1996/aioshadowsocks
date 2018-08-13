import logging
import asyncio


class ServerPool:
    _instance = None

    user_ids = list()
    tcp_server_ids = list()
    udp_server_ids = list()

    # {'user_id':{
    #              'user':<user instance>,
    #              'handlers:[<local handler>,]')}
    user_handlers = {}

    def __new__(cls, *args, **kw):
        if not cls._instance:
            cls._instance = super(ServerPool, cls).__new__(cls, *args, **kw)
        return cls._instance

    @classmethod
    def _check_user_exist(cls, user_id):
        return user_id in cls.user_ids

    @classmethod
    def _add_user_handler(cls, user):
        cls.user_ids.append(user.user_id)
        cls.user_handlers[user.user_id] = {'user': user, 'handlers': list()}

    @classmethod
    def check_tcp_server(cls, server_id):
        return server_id in cls.tcp_server_ids

    @classmethod
    def check_udp_server(cls, server_id):
        return server_id in cls.udp_server_ids

    @classmethod
    def add_tcp_server(cls, server_id, user, server_instance):
        if cls._check_user_exist(user.user_id) is False:
            cls._add_user_handler(user)

        cls.tcp_server_ids.append(server_id)
        cls.user_handlers[user.user_id]['handlers'].append(server_instance)

    @classmethod
    def add_udp_server(cls, server_id, user, server_instance):
        if cls._check_user_exist(user.user_id) is False:
            cls._add_user_handler(user)

        cls.udp_server_ids.append(server_id)
        cls.user_handlers[user.user_id]['handlers'].append(server_instance)


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
