import asyncio
import json
import logging
from collections import defaultdict

import peewee as pw

from shadowsocks.core import LocalTCP, LocalUDP
from shadowsocks.ratelimit import TrafficRateLimit
from shadowsocks.mdb import BaseModel, HttpSessionMixin, JsonField


class User(BaseModel, HttpSessionMixin):

    __attr_protected__ = {"user_id"}
    __attr_accessible__ = {"port", "method", "password", "enable", "speed_limit"}

    user_id = pw.IntegerField(primary_key=True, unique=True)
    port = pw.IntegerField(unique=True)
    method = pw.CharField()
    password = pw.CharField()
    enable = pw.BooleanField(default=True)
    speed_limit = pw.IntegerField(default=0)

    @classmethod
    def create_or_update_from_json(cls, path):
        with open(path, "r") as f:
            data = json.load(f)
        for user_data in data["users"]:
            cls.create_or_update_user_from_data(user_data)

    @classmethod
    def create_or_update_from_remote(cls):
        res = cls.http_session.request("get")
        for user_data in res.json()["users"]:
            cls.create_or_update_user_from_data(user_data)

    @classmethod
    def create_or_update_user_from_data(cls, data):
        user_id = data.pop("user_id")
        user, created = cls.get_or_create(user_id=user_id, defaults=data)
        if not created:
            user.update_from_dict(data)
            user.save()
        logging.debug(f"正在创建/更新用户:{user}的数据")
        return user

    @classmethod
    def init_user_servers(cls):
        for user in cls.select():
            data = user.to_dict()
            user_id = data.pop("user_id")
            us, _ = UserServer.get_or_create(user_id=user_id, defaults=data)
            loop = asyncio.get_event_loop()
            loop.create_task(us.init_server(user))

    @property
    def server(self):
        return UserServer.get_by_id(self.user_id)


class UserServer(BaseModel, HttpSessionMixin):

    __attr_accessible__ = {"port", "method", "password", "enable"}

    HOST = "0.0.0.0"
    __running_servers__ = defaultdict(dict)
    __user_limiters__ = defaultdict(dict)

    user_id = pw.IntegerField(primary_key=True)
    port = pw.IntegerField(unique=True)
    method = pw.CharField()
    password = pw.CharField()
    enable = pw.BooleanField(default=True)

    # need sync field
    upload_traffic = pw.BigIntegerField(default=0)
    download_traffic = pw.BigIntegerField(default=0)
    ip_list = JsonField(default=[])

    @classmethod
    def shutdown(cls):
        for us in cls.select():
            us.close_server()

    @classmethod
    def flush_data_to_remote(cls):
        data = []
        need_reset_user_id = []
        fields = [
            cls._meta.fields["user_id"],
            cls._meta.fields["upload_traffic"],
            cls._meta.fields["download_traffic"],
            cls._meta.fields["ip_list"],
        ]
        for us in cls.select().where(cls.download_traffic > 0):
            data.append(us.to_dict(only=fields))
            need_reset_user_id.append(us.user_id)
        res = cls.http_session.request("post", json={"data": data})
        res and cls.update(upload_traffic=0, download_traffic=0, ip_list=[]).where(
            cls.user_id << need_reset_user_id
        ).execute()

    @property
    def host(self):
        return "0.0.0.0"

    @property
    def used_traffic(self):
        return self.upload_traffic + self.download_traffic

    @property
    def is_running(self):
        return self.user_id in self.__running_servers__

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

    @property
    def limiter(self):
        return self.__user_limiters__.get(self.user_id)

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

    @limiter.setter
    def limiter(self, limiter):
        self.__user_limiters__[self.user_id] = limiter

    async def init_server(self, user):
        self.is_running and self.check_user_server(user)

        if self.is_running or user.enable is False:
            return
        loop = asyncio.get_event_loop()
        try:
            tcp_server = await loop.create_server(LocalTCP(user), self.HOST, user.port)
            udp_server, _ = await loop.create_datagram_endpoint(
                LocalUDP(user), (self.HOST, user.port)
            )
            self.tcp_server = tcp_server
            self.udp_server = udp_server
            self.limiter = TrafficRateLimit(user.speed_limit, user.speed_limit)
            self.update_from_dict(user.to_dict())
            self.save()
            logging.info(
                "user:{} method:{} password:{} port:{} 已启动".format(
                    user, user.method, user.password, user.port
                )
            )
        except OSError as e:
            logging.warning(e)

    def check_user_server(self, user):
        need_check_fields = ["method", "port", "password"]
        for field in need_check_fields:
            if getattr(self, field) != getattr(user, field) or user.enable is False:
                self.close_server()
                return

    def close_server(self):

        if self.user_id not in self.__running_servers__:
            return

        server_data = self.__running_servers__.pop(self.user_id)
        server_data["tcp"].close()
        server_data["udp"].close()
        logging.info(f"user:{self.user_id} port:{self.port} 已关闭!")

    def record_ip(self, peername):
        if not peername:
            return
        ip = peername[0]
        self.ip_list.append(ip)
        self.ip_list = list(set(self.ip_list))
        self.save(only=["ip_list"])

    def record_traffic(self, used_u, used_d):
        cls = type(self)
        cls.update(
            upload_traffic=cls.upload_traffic + used_u,
            download_traffic=cls.download_traffic + used_d,
        ).where(cls.user_id == self.user_id).execute()

    def check_is_limited(self, data_lens):
        limiter = self.limiter
        if limiter.consume(data_lens):
            logging.warning(
                f"reach rate limit: {limiter.human_rate}Mbps user_id: {self.user_id}"
            )
            return True
        return False
