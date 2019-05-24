import logging
import asyncio
import peewee as pw

from shadowsocks.mdb import BaseModel
from shadowsocks.core import LocalTCP, LocalUDP


class User(BaseModel):

    __attr_protected__ = {"upload_traffic", "download_traffic"}

    user_id = pw.IntegerField(primary_key=True)
    port = pw.IntegerField(unique=True)
    method = pw.CharField()
    password = pw.CharField()

    upload_traffic = pw.BigIntegerField(default=0)
    download_traffic = pw.BigIntegerField(default=0)

    @property
    def host(self):
        return "0.0.0.0"

    @property
    def used_traffic(self):
        return self.upload_traffic + self.download_traffic

    @classmethod
    def create_or_update_from_remote(cls):
        from transfer.json_transfer import JsonTransfer

        c = JsonTransfer("defaultconfig.json")
        configs = c.get_all_user_configs()
        for user_config in configs:
            user_id = user_config.pop("user_id")
            user, created = cls.get_or_create(user_id=user_id, defaults=user_config)
            if not created:
                user.update_from_dict(user_config)
                user.save()
            logging.info(f"正在创建/更新用户:{user}的数据 当前流量{user.used_traffic}")

    @classmethod
    def init_user_servers(cls):
        for user in cls.select():
            us, _ = UserServer.get_or_create(user_id=user.user_id)
            loop = asyncio.get_event_loop()
            loop.create_task(us.init_server())


class UserServer(BaseModel):

    __running_servers__ = {}

    user_id = pw.IntegerField(primary_key=True)

    async def init_server(self):
        if self.user_id in self.__running_servers__:
            return

        loop = asyncio.get_event_loop()
        try:
            user = User.get_by_id(self.user_id)
            tcp_server = await loop.create_server(LocalTCP(user), user.host, user.port)
            udp_server, _ = await loop.create_datagram_endpoint(
                LocalUDP(user), (user.host, user.port)
            )
            self.__running_servers__[self.user_id] = {
                "tcp": tcp_server,
                "udp": udp_server,
            }
            logging.info(f"user:{user} password:{user.password} 在端口:{user.port} 启动啦")
        except OSError as e:
            print(self.__running_servers__)
            logging.warning(e)
