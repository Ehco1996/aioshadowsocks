from __future__ import annotations

import logging
from typing import List

import peewee as pw
from cryptography.exceptions import InvalidTag

from shadowsocks import protocol_flag as flag
from shadowsocks.ciphers import SUPPORT_METHODS
from shadowsocks.mdb import BaseModel, IPSetField, db
from shadowsocks.metrics import FIND_ACCESS_USER_TIME


class User(BaseModel):

    __attr_protected__ = {"user_id"}
    __attr_accessible__ = {"port", "method", "password", "enable", "speed_limit"}

    user_id = pw.IntegerField(primary_key=True, unique=True)
    port = pw.IntegerField(index=True)
    method = pw.CharField()
    password = pw.CharField(unique=True)
    enable = pw.BooleanField(default=True)
    access_order = pw.BigIntegerField(
        index=True, default=0
    )  # NOTE find_access_user order
    need_sync = pw.BooleanField(default=False, index=True)
    # metrics field
    ip_list = IPSetField(default=set())
    tcp_conn_num = pw.IntegerField(default=0)
    upload_traffic = pw.BigIntegerField(default=0)
    download_traffic = pw.BigIntegerField(default=0)

    def __str__(self):
        return f"[{self.user_id}-{self.access_order}]"

    @classmethod
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
        return cls.select().where(cls.port == port).order_by(cls.access_order.desc())

    @classmethod
    @db.atomic("EXCLUSIVE")
    def create_or_update_by_user_data_list(cls, user_data_list):
        if not cls.select().first():
            # bulk create
            users = [
                cls(
                    user_id=u["user_id"],
                    enable=u["enable"],
                    method=u["method"],
                    password=u["password"],
                    port=u["port"],
                )
                for u in user_data_list
            ]
            cls.bulk_create(users, batch_size=500)
        else:
            db_user_dict = {
                u.user_id: u
                for u in cls.select(
                    cls.user_id, cls.enable, cls.method, cls.password, cls.port
                )
            }
            enable_user_ids = []
            need_update_or_create_users = []
            for user_data in user_data_list:
                user_id = user_data["user_id"]
                enable_user_ids.append(user_id)
                db_user = db_user_dict.get(user_id)
                # 找到配置变化了的用户
                if (
                    not db_user
                    or db_user.port != user_data["port"]
                    or db_user.enable != user_data["enable"]
                    or db_user.method != user_data["method"]
                    or db_user.password != user_data["password"]
                ):
                    need_update_or_create_users.append(user_data)
            for user_data in need_update_or_create_users:
                cls._create_or_update_user_from_data(user_data)
            sync_msg = "sync users: enable_user_cnt: {} updated_user_cnt: {},deleted_user_cnt:{}".format(
                len(enable_user_ids),
                len(need_update_or_create_users),
                cls.delete().where(cls.user_id.not_in(enable_user_ids)).execute(),
            )
            logging.info(sync_msg)

    @classmethod
    @db.atomic("EXCLUSIVE")
    def get_and_reset_need_sync_user_metrics(cls) -> List[User]:
        fields = [
            User.user_id,
            User.ip_list,
            User.tcp_conn_num,
            User.upload_traffic,
            User.download_traffic,
        ]
        users = list(User.select(*fields).where(User.need_sync == True))
        empyt_set = set()
        User.update(
            ip_list=empyt_set, upload_traffic=0, download_traffic=0, need_sync=False
        ).where(User.need_sync == True).execute()
        return users

    @classmethod
    @FIND_ACCESS_USER_TIME.time()
    def find_access_user(cls, port, method, ts_protocol, first_data) -> User:
        cipher_cls = SUPPORT_METHODS[method]
        access_user = None
        for user in cls.list_by_port(port).iterator():
            try:
                cipher = cipher_cls(user.password)
                if ts_protocol == flag.TRANSPORT_TCP:
                    cipher.decrypt(first_data)
                else:
                    cipher.unpack(first_data)
                access_user = user
                break
            except InvalidTag:
                pass
        if access_user:
            # NOTE 记下成功访问的用户，下次优先找到他
            access_user.access_order += 1
            access_user.save(only=[cls.access_order])
        return access_user

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
