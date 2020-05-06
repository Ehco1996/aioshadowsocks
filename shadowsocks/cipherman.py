from __future__ import annotations

import copy
import logging
from typing import List

from shadowsocks.ciphers import AES256CFB, NONE, ChaCha20IETFPoly1305
from shadowsocks.mdb.models import User
from shadowsocks.metrics import (
    DECRYPT_DATA_TIME,
    ENCRYPT_DATA_TIME,
    FIND_ACCESS_USER_TIME,
    NETWORK_TRANSMIT_BYTES,
)


class CipherMan:

    SUPPORT_METHODS = {
        "aes-256-cfb": AES256CFB,
        "none": NONE,
        "chacha20-ietf-poly1305": ChaCha20IETFPoly1305,
    }

    # TODO 流量、链接数限速

    @classmethod
    def get_cipher_by_port(cls, port) -> CipherMan:
        user_list = User.list_by_port(port)
        if len(user_list) == 1:
            access_user = user_list[0]
        else:
            access_user = None
        return cls(user_list, access_user=access_user)

    def __init__(self, user_list: List[User] = None, access_user: User = None):
        self.user_list = user_list
        self.access_user = access_user
        self.cipher = None

        if self.access_user:
            self.method = access_user.method
        else:
            self.method = user_list[0].method  # NOTE 所有的user用的加密方式必须是一种
        self.cipher_cls = self.SUPPORT_METHODS.get(self.method)

    @FIND_ACCESS_USER_TIME.time()
    def find_access_user(self, first_data: bytes) -> User:
        """
        通过auth校验来找到正确的user
        TODO 1. 复用data 2. 寻找user的算法
        """
        import time

        t1 = time.time()
        success_user = None
        for user in self.user_list:
            payload = copy.copy(first_data)
            cipher = self.cipher_cls(user.password)
            try:
                # TODO 如果res是空说明还没收集到足够多的data
                res = cipher.decrypt(payload)
                success_user = user
                break
            except ValueError as e:
                if e.args[0] != "MAC check failed":
                    raise e
        logging.info(
            f"用户:{success_user} 一共寻找了{len(self.user_list)}个user,共花费{(time.time()-t1)*1000}ms"
        )
        return success_user

    @ENCRYPT_DATA_TIME.time()
    def encrypt(self, data: bytes):
        if not self.cipher:
            self.cipher = self.cipher_cls(self.access_user.password)
        self.access_user and self.access_user.record_traffic(len(data), len(data))
        NETWORK_TRANSMIT_BYTES.inc(len(data))
        return self.cipher.encrypt(data)

    @DECRYPT_DATA_TIME.time()
    def decrypt(self, data: bytes):
        if not self.cipher:
            if not self.access_user:
                self.access_user = self.find_access_user(data)
            if not self.access_user:
                raise RuntimeError("没有找到合法的用户")
            if not self.access_user.enable:
                raise RuntimeError(f"用户: {self.access_user} enable = False")
            self.cipher = self.cipher_cls(self.access_user.password)
        self.access_user and self.access_user.record_traffic(len(data), len(data))
        NETWORK_TRANSMIT_BYTES.inc(len(data))
        return self.cipher.decrypt(data)

    def incr_user_tcp_num(self, num: int):
        self.access_user and self.access_user.incr_tcp_conn_num(num)

    def record_user_ip(self, peername):
        self.access_user and self.access_user.record_ip(peername)
