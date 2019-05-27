import asyncio
import json
import logging

import peewee as pw

from shadowsocks.core import LocalTCP, LocalUDP
from shadowsocks.mdb import BaseModel, HttpSessionMixin, JSONCharField


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
    ip_list = JSONCharField(default=[])

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
            # NOTE 兼容api
            user_config.pop("id", None)
            user, created = cls.get_or_create(user_id=user_id, defaults=user_config)
            if not created:
                user.update_from_dict(user_config)
                user.save()
            logging.debug(f"正在创建/更新用户:{user}的数据 当前流量{user.used_traffic}")

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
            cls._meta.fields["ip_list"],
        ]
        need_reset_user_id = []
        for user in cls.select().where(cls.download_traffic > 0):
            data.append(user.to_dict(only=need_fields))
            need_reset_user_id.append(user.user_id)
        res = cls.http_session.request("post", json={"data": data})
        res and cls.update(upload_traffic=0, download_traffic=0, ip_list=[]).where(
            cls.user_id << need_reset_user_id
        ).execute()

    def record_traffic(self, used_u, used_d):
        User.update(
            upload_traffic=User.upload_traffic + used_u,
            download_traffic=User.download_traffic + used_d,
        ).where(User.user_id == self.user_id).execute()

    def record_ip(self, peername):
        ip = peername[0]
        user = User.get_by_id(self.user_id)
        user.ip_list.append(ip)
        user.ip_list = list(set(user.ip_list))
        user.save(only=["ip_list"])


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
            logging.info(
                "user_id:{} method:{} password:{} port:{} 已启动".format(
                    user.user_id, user.method, user.password, user.port
                )
            )
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
        logging.info(f"user_id:{user} prot:{user.port} 已关闭!")
