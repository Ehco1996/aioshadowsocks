from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict

import peewee as pw

from shadowsocks.mdb import BaseModel, HttpSessionMixin
from shadowsocks.ratelimit import TcpConnRateLimit, TrafficRateLimit


class User(BaseModel, HttpSessionMixin):

    __attr_protected__ = {"user_id"}
    __attr_accessible__ = {"port", "method", "password", "enable", "speed_limit"}

    user_id = pw.IntegerField(primary_key=True, unique=True)
    port = pw.IntegerField(index=True)
    method = pw.CharField()
    password = pw.CharField()
    enable = pw.BooleanField(default=True)
    speed_limit = pw.IntegerField(default=0)

    @classmethod
    def list_by_port(cls, port) -> User:
        return cls.select().where(cls.port == port)

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


class UserServer(BaseModel, HttpSessionMixin):
    HOST = "0.0.0.0"
    METRIC_FIELDS = {"upload_traffic", "download_traffic", "ip_list"}

    __attr_accessible__ = {"port", "method", "password", "enable"}

    __running_servers__ = defaultdict(dict)
    __user_metrics__ = defaultdict(dict)
    __user_limiters__ = defaultdict(dict)
    __active_user_ids__ = []

    user_id = pw.IntegerField(primary_key=True)
    port = pw.IntegerField(unique=True)
    method = pw.CharField()
    password = pw.CharField()
    enable = pw.BooleanField(default=True)

    @classmethod
    def get_total_connection_count(cls):
        cnt = 0
        for us in cls.select().where(cls.user_id << cls.__active_user_ids__):
            cnt += us.tcp_limiter.tcp_conn_num
        return cnt

    @classmethod
    def flush_metrics_to_remote(cls, url):
        data = []
        need_reset_user_ids = []
        for user_id, metric in cls.__user_metrics__.items():
            if (metric["upload_traffic"] + metric["download_traffic"]) > 0:
                data.append(
                    {
                        "user_id": user_id,
                        "upload_traffic": metric["upload_traffic"],
                        "download_traffic": metric["download_traffic"],
                        "ip_list": list(metric["ip_list"]),
                        "tcp_conn_num": cls.get_by_id(user_id).tcp_limiter.tcp_conn_num,
                    }
                )
                need_reset_user_ids.append(user_id)
        cls.http_session.request("post", url, json={"data": data})
        for user_id in need_reset_user_ids:
            cls.__user_metrics__[user_id].update(cls.init_new_metric())
        # set active user
        cls.__active_user_ids__ = need_reset_user_ids

    @staticmethod
    def init_new_metric():
        return {"upload_traffic": 0, "download_traffic": 0, "ip_list": set()}

    @property
    def metrics(self):
        return self.__user_metrics__[self.user_id]

    @metrics.setter
    def metrics(self, data):
        self.__user_metrics__[self.user_id].update(data)

    def check_user_server(self, user):
        need_check_fields = ["method", "port", "password"]
        for field in need_check_fields:
            if getattr(self, field) != getattr(user, field) or user.enable is False:
                self.close_server()
                return

    def record_ip(self, peername):
        if not peername:
            return
        self.metrics["ip_list"].add(peername[0])

    def record_traffic(self, used_u, used_d):
        self.metrics["upload_traffic"] += used_u
        self.metrics["download_traffic"] += used_d

    def record_traffic_rate(self, data_lens):
        self.traffic_limiter.consume(data_lens)
