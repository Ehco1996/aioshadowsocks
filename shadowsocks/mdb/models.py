from __future__ import annotations

import logging

from cryptography.exceptions import InvalidTag
from tortoise import fields
from tortoise.expressions import F

from shadowsocks import protocol_flag as flag
from shadowsocks.ciphers import SUPPORT_METHODS
from shadowsocks.mdb import BaseModel, IPSetField
from shadowsocks.metrics import FIND_ACCESS_USER_TIME


class User(BaseModel):

    __attr_protected__ = {"user_id"}
    __attr_accessible__ = {"port", "method", "password", "enable", "speed_limit"}

    user_id = fields.BigIntField(unique=True)
    port = fields.BigIntField(index=True)
    method = fields.CharField(max_length=50)
    password = fields.CharField(unique=True, max_length=50)
    enable = fields.BooleanField(default=True)
    access_order = fields.BigIntField(
        index=True, default=0
    )  # NOTE find_access_user order
    need_sync = fields.BooleanField(default=False, index=True)
    # metrics field
    ip_list = IPSetField(default=set(), max_length=50)
    tcp_conn_num = fields.BigIntField(default=0)
    upload_traffic = fields.BigIntField(default=0)
    download_traffic = fields.BigIntField(default=0)

    def __str__(self) -> str:
        return f"[user_id:{self.user_id}-order:{self.access_order}]"

    @classmethod
    async def _create_or_update_user_from_data(cls, data):
        user_id = data.pop("user_id")
        user, _ = await cls.update_or_create(user_id=user_id, defaults=data)
        logging.debug(f"正在创建/更新用户:{user}的数据")
        return user

    @classmethod
    async def create_or_update_by_user_data_list(cls, user_data_list):
        # TODO to bulk
        db_user_dict = {
            u["user_id"]: u
            for u in await User.all().values(
                "user_id", "enable", "method", "password", "port"
            )
        }
        enable_user_ids = []
        need_update_or_create_users = []
        for user_data in user_data_list:
            user_id = user_data["user_id"]
            enable_user_ids.append(user_id)
            if user_data != db_user_dict.get(user_id):
                need_update_or_create_users.append(user_data)
        for user_data in need_update_or_create_users:
            await cls._create_or_update_user_from_data(user_data)
        cnt = await cls.filter(user_id__not_in=enable_user_ids).delete()
        cnt and logging.info(f"delete out of traffic user cnt: {cnt}")

    @classmethod
    async def reset_need_sync_user_metrics(cls):
        empty_ip_list = set()
        return (
            await cls.filter(need_sync=True)
            .select_for_update()
            .update(
                ip_list=empty_ip_list,
                upload_traffic=0,
                download_traffic=0,
                need_sync=False,
            )
        )

    @classmethod
    @FIND_ACCESS_USER_TIME.time()
    async def find_access_user(cls, port, method, ts_protocol, first_data) -> User:
        cipher_cls = SUPPORT_METHODS[method]
        access_user = None
        users = await cls.list_by_port(port).limit(10)
        for user in users:
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
            await access_user.save(update_fields=["access_order"])
        return access_user

    async def record_ip(self, peername):
        if not peername:
            return
        self.ip_list.add(peername[0])
        return (
            await User.filter(user_id=self.user_id)
            .select_for_update()
            .update(ip_list=self.ip_list, need_sync=True)
        )

    async def record_traffic(self, used_u, used_d):
        return (
            await User.filter(user_id=self.user_id)
            .select_for_update()
            .update(
                download_traffic=F("download_traffic") + used_d,
                upload_traffic=F("upload_traffic") + used_u,
                need_sync=True,
            )
        )

    async def incr_tcp_conn_num(self, num):
        return (
            await User.filter(user_id=self.user_id)
            .select_for_update()
            .update(tcp_conn_num=F("tcp_conn_num") + num, need_sync=True)
        )

    @classmethod
    def list_need_sync_user(cls):
        return cls.filter(need_sync=True)

    @classmethod
    def list_by_port(cls, port):
        return cls.filter(port=port).order_by("-access_order")
