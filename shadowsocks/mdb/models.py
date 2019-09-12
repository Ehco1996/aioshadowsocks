import asyncio
import json
import logging
from collections import defaultdict

import peewee as pw

from shadowsocks.core import LocalTCP, LocalUDP
from shadowsocks.mdb import BaseModel, HttpSessionMixin, cached_property


class User(BaseModel, HttpSessionMixin):

    __attr_protected__ = {"user_id"}
    __attr_accessible__ = {"port", "method", "password", "enable"}

    user_id = pw.IntegerField(primary_key=True, unique=True)
    port = pw.IntegerField(unique=True)
    method = pw.CharField()
    password = pw.CharField()
    enable = pw.BooleanField(default=True)

    @classmethod
    def create_or_update_from_json(cls, path):
        with open(path, "r") as f:
            data = json.load(f)
        for user_data in data["users"]:
            cls.create_or_update_user_from_data(user_data)

    @classmethod
    def create_or_update_from_remote(cls, url):
        res = cls.http_session.request("get", url)
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
        loop = asyncio.get_event_loop()
        for user in cls.select():
            data = user.to_dict()
            user_id = data.pop("user_id")
            us, _ = UserServer.get_or_create(user_id=user_id, defaults=data)
            loop.create_task(us.init_server(user))

    @cached_property
    def server(self):
        return UserServer.get_by_id(self.user_id)


class UserServer(BaseModel, HttpSessionMixin):
    HOST = "0.0.0.0"
    METRIC_FIELDS = {"upload_traffic", "download_traffic", "tcp_conn_num", "ip_list"}

    __attr_accessible__ = {"port", "method", "password", "enable"}

    __running_servers__ = defaultdict(dict)

    __user_metrics__ = defaultdict(dict)

    user_id = pw.IntegerField(primary_key=True)
    port = pw.IntegerField(unique=True)
    method = pw.CharField()
    password = pw.CharField()
    enable = pw.BooleanField(default=True)

    @classmethod
    def shutdown(cls):
        for us in cls.select():
            us.close_server()

    @classmethod
    def flush_metrics_to_remote(cls, url):
        data = []
        need_reset_user_ids = []
        for user_id, metric in cls.__user_metrics__.items():
            if (metric["upload_traffic"] + metric["download_traffic"]) > 0:
                metric["user_id"] = user_id
                metric["ip_list"] = list(metric["ip_list"])
                data.append(metric)
                need_reset_user_ids.append(user_id)
        cls.http_session.request("post", url, json={"data": data})
        for user_id in need_reset_user_ids:
            new_metric = cls.init_new_metric()
            new_metric.pop("tcp_conn_num")
            cls.__user_metrics__[user_id].update(new_metric)

    @property
    def host(self):
        return "0.0.0.0"

    @property
    def is_running(self):
        return self.user_id in self.__running_servers__

    @property
    def tcp_server(self):
        return self.__running_servers__[self.user_id].get("tcp")

    @property
    def udp_server(self):
        return self.__running_servers__[self.user_id].get("udp")

    @property
    def metrics(self):
        return self.__user_metrics__[self.user_id]

    @metrics.setter
    def metrics(self, data):
        self.__user_metrics__[self.user_id].update(data)

    @property
    def tcp_conn_num(self):
        return self.metrics["tcp_conn_num"]

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

    @staticmethod
    def init_new_metric():
        return {
            "upload_traffic": 0,
            "download_traffic": 0,
            "tcp_conn_num": 0,
            "ip_list": set(),
        }

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
            self.metrics = self.init_new_metric()
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
        self.metrics["ip_list"].add(peername[0])

    def record_traffic(self, used_u, used_d):
        self.metrics["upload_traffic"] += used_u
        self.metrics["download_traffic"] += used_d

    def incr_tcp_conn_num(self, num):
        self.metrics["tcp_conn_num"] += num
