import asyncio
import json
import logging

import peewee as pw

from shadowsocks.core import LocalTCP, LocalUDP
from shadowsocks.mdb import BaseModel, HttpSessionMixin


class User(BaseModel, HttpSessionMixin):

    __attr_protected__ = {"used_u", "used_d", "peernames"}

    user_id = pw.IntegerField(primary_key=True, unique=True)
    port = pw.IntegerField(unique=True)
    method = pw.CharField()
    password = pw.CharField()
    enable = pw.BooleanField(default=True)

    # need sync field
    upload_traffic = pw.BigIntegerField(default=0)
    download_traffic = pw.BigIntegerField(default=0)
    peernames = pw.CharField(null=True)  # Use set to store peername

    @property
    def host(self):
        return "0.0.0.0"

    @property
    def used_traffic(self):
        return self.upload_traffic + self.download_traffic

    @classmethod
    def create_or_update_from_json(cls, path):
        with open(path, "r") as f:
            data = json.load(f)
        data and cls.create_or_update_user_from_data(data["users"])

    @classmethod
    def create_or_update_from_remote(cls):
        res = cls.http_session.request("get")
        res and cls.create_or_update_user_from_data(res.json()["users"])

    @classmethod
    def create_or_update_user_from_data(cls, data):
        # TODO 用户更换端口/加密方式时
        for user_config in data:
            user_id = user_config.pop("user_id")
            user, created = cls.get_or_create(user_id=user_id, defaults=user_config)
            if not created:
                user.update_from_dict(user_config)
                user.save()
            logging.info(f"正在创建/更新用户:{user}的数据 当前流量{user.used_traffic}")

    @classmethod
    def init_user_servers(cls):
        for user in cls.select().where(cls.enable == True):
            us, _ = UserServer.get_or_create(user_id=user.user_id)
            loop = asyncio.get_event_loop()
            loop.create_task(us.init_server())

    @classmethod
    def shutdown_user_servers(cls):
        for user in cls.select():
            us, _ = UserServer.get_or_create(user_id=user.user_id)
            us.close_server()

    @classmethod
    def flush_data_to_remote(cls):
        data = []
        need_fields = [
            cls._meta.fields["user_id"],
            cls._meta.fields["upload_traffic"],
            cls._meta.fields["download_traffic"],
            cls._meta.fields["peernames"],
        ]

        query = [cls.download_traffic > 0]
        for user in cls.select().where(*query):
            data.append(user.to_dict(only=need_fields))
        if data:
            res = cls.http_session.request("post", json={"data": data})
            res and cls.update(
                upload_traffic=0, download_traffic=0, peernames=None
            ).where(*query).execute()

    def record_traffic(self, used_u, used_d):
        self.download_traffic += used_d
        self.upload_traffic += used_u
        self.save(only=["upload_traffic", "download_traffic"])

    def record_peername(self, peername):
        # only record ip
        if not self.peernames:
            self.peernames = {peername[0]}
        else:
            self.peernames.add(peername[0])
        self.save(only=["peernames"])


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
            logging.warning(e)

    def close_server(self):
        self.delete_instance()

        if self.user_id not in self.__running_servers__:
            return

        server_data = self.__running_servers__.pop(self.user_id)
        server_data["tcp"].close()
        server_data["udp"].close()
        user = User.get_by_id(self.user_id)
        logging.info(f"user_id:{user} password:{user.password} 在端口:{user.port} 已关闭")

