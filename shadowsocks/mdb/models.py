from __future__ import annotations

import json
import logging
import asyncio

import peewee as pw

from shadowsocks.mdb import BaseModel, HttpSessionMixin, IPSetField, db


class User(BaseModel, HttpSessionMixin):

    __attr_protected__ = {"user_id"}
    __attr_accessible__ = {"port", "method", "password", "enable", "speed_limit"}

    user_id = pw.IntegerField(primary_key=True, unique=True)
    port = pw.IntegerField(index=True)
    method = pw.CharField()
    password = pw.CharField(unique=True)
    enable = pw.BooleanField(default=True)
    speed_limit = pw.IntegerField(default=0)
    access_order = pw.BigIntegerField(
        index=True, default=0
    )  # NOTE find_access_user order
    need_sync = pw.BooleanField(default=False, index=True)
    # metrics field
    ip_list = IPSetField(default=set())
    tcp_conn_num = pw.IntegerField(default=0)
    upload_traffic = pw.BigIntegerField(default=0)
    download_traffic = pw.BigIntegerField(default=0)

    @classmethod
    @db.atomic("EXCLUSIVE")
    def _create_or_update_user_from_data(cls, data):
        user_id = data.pop("user_id")
        user, created = cls.get_or_create(user_id=user_id, defaults=data)
        if not created:
            user.update_from_dict(data)
            user.save()
        logging.debug(f"正在创建/更新用户:{user}的数据")
        return user

    @classmethod
    def list_by_port(cls, port):
        fields = [
            cls.user_id,
            cls.method,
            cls.password,
            cls.enable,
            cls.ip_list,
            cls.access_order,
        ]
        return (
            cls.select(*fields)
            .where(cls.port == port)
            .order_by(cls.access_order.desc())
        )

    @classmethod
    def create_or_update_from_json(cls, path):
        with open(path, "r") as f:
            data = json.load(f)
        for user_data in data["users"]:
            cls._create_or_update_user_from_data(user_data)

    @classmethod
    def create_or_update_from_remote(cls, url):
        res = cls.http_session.request("get", url)
        for user_data in res.json()["users"]:
            cls._create_or_update_user_from_data(user_data)

    @classmethod
    @db.atomic("EXCLUSIVE")
    def flush_metrics_to_remote(cls, url):
        data = []
        fields = [
            cls.user_id,
            cls.ip_list,
            cls.tcp_conn_num,
            cls.upload_traffic,
            cls.download_traffic,
        ]
        users = cls.select(*fields).where(cls.need_sync == True)
        cls.update(
            ip_list=set(), upload_traffic=0, download_traffic=0, need_sync=False
        ).where(cls.need_sync == True).execute()
        for user in users:
            data.append(
                {
                    "user_id": user.user_id,
                    "ip_list": list(user.ip_list),
                    "tcp_conn_num": user.tcp_conn_num,
                    "upload_traffic": user.upload_traffic,
                    "download_traffic": user.download_traffic,
                }
            )
        cls.http_session.request("post", url, json={"data": data})

    @db.atomic("EXCLUSIVE")
    def record_ip(self, peername):
        if not peername:
            return
        self.ip_list.add(peername[0])
        User.update(ip_list=self.ip_list, need_sync=True).where(
            User.user_id == self.user_id
        ).execute()

    @db.atomic("EXCLUSIVE")
    def record_traffic(self, used_u, used_d):
        User.update(
            download_traffic=User.download_traffic + used_d,
            upload_traffic=User.upload_traffic + used_u,
            need_sync=True,
        ).where(User.user_id == self.user_id).execute()

    @db.atomic("EXCLUSIVE")
    def incr_tcp_conn_num(self, num):
        User.update(tcp_conn_num=User.tcp_conn_num + num, need_sync=True).where(
            User.user_id == self.user_id
        ).execute()
