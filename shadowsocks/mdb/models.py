import asyncio
import json
import logging
from collections import defaultdict

import peewee as pw

from shadowsocks.core import LocalTCP, LocalUDP
from shadowsocks.mdb import BaseModel, HttpSessionMixin, JsonField


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
    ip_list = JsonField(default=[])

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
        for user in cls.select():
            us, _ = UserServer.get_or_create(user_id=user.user_id)
            loop = asyncio.get_event_loop()
            loop.create_task(us.init_server(user))

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

    __running_servers__ = defaultdict(dict)

    user_id = pw.IntegerField(primary_key=True)

    @property
    def tcp_server(self):
        try:
            return self.__running_servers__[self.user_id]["tcp"]
        except KeyError:
            return None

    @property
    def udp_server(self):
        try:
            return self.__running_servers__[self.user_id]["udp"]
        except KeyError:
            return None

    @tcp_server.setter
    def tcp_server(self, server):
        if self.tcp_server:
            self.tcp_server.close()
        self.__running_servers__[self.user_id]["tcp"] = server

    @udp_server.setter
    def udp_server(self, server):
        if self.udp_server:
            self.udp_server.close()
        self.__running_servers__[self.user_id]["udp"] = server

    @property
    def is_running(self):
        return self.user_id in self.__running_servers__

    async def init_server(self, user):
        self.is_running and self.check_user_server(user)

        if self.is_running or not user.enable:
            return
        loop = asyncio.get_event_loop()
        try:
            tcp_server = await loop.create_server(LocalTCP(user), user.host, user.port)
            udp_server, _ = await loop.create_datagram_endpoint(
                LocalUDP(user), (user.host, user.port)
            )
            self.tcp_server = tcp_server
            self.udp_server = udp_server
            logging.info(
                "user_id:{} method:{} password:{} port:{} 已启动".format(
                    user.user_id, user.method, user.password, user.port
                )
            )
        except OSError as e:
            logging.warning(e)

    def check_user_server(self, user):
        # get running server user
        tcp_user = self.tcp_server._protocol_factory.user
        if (
            not user.enable
            or tcp_user.port != user.port
            or tcp_user.password != user.password
        ):
            self.close_server()

    def close_server(self):
        self.delete_instance()

        if self.user_id not in self.__running_servers__:
            return

        user = self.tcp_server._protocol_factory.user
        server_data = self.__running_servers__.pop(self.user_id)
        server_data["tcp"].close()
        server_data["udp"].close()
        logging.info(f"user_id:{user} port:{user.port} 已关闭!")
