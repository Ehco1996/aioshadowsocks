from __future__ import annotations

import logging
import time
from typing import List

from bloom_filter import BloomFilter

from shadowsocks.ciphers import (
    AES128GCM,
    AES256CFB,
    AES256GCM,
    CHACHA20IETFPOLY1305,
    NONE,
)
from shadowsocks.mdb.models import User
from shadowsocks.metrics import (
    DECRYPT_DATA_TIME,
    ENCRYPT_DATA_TIME,
    FIND_ACCESS_USER_TIME,
    NETWORK_TRANSMIT_BYTES,
)


class CipherMan:

    SUPPORT_METHODS = {
        "none": NONE,
        "aes-256-cfb": AES256CFB,
        "aes-128-gcm": AES128GCM,
        "aes-256-gcm": AES256GCM,
        "chacha20-ietf-poly1305": CHACHA20IETFPOLY1305,
    }
    bf = BloomFilter()

    # TODO 流量、链接数限速

    def __init__(self, user_list: List[User] = None, access_user: User = None):
        self.user_list = user_list
        self.access_user = access_user
        self.last_access_user = None
        self.cipher = None
        self._buffer = bytearray()

        if self.access_user:
            self.method = access_user.method
        else:
            self.method = user_list[0].method  # NOTE 所有的user用的加密方式必须是一种

        self.cipher_cls = self.SUPPORT_METHODS.get(self.method)
        # NOTE 解第一个包的时候必须收集到足够多的数据:salt + payload_len(2) + tag
        self._first_data_len = self.cipher_cls.SALT_SIZE + 2 + self.cipher_cls.TAG_SIZE

    @classmethod
    def get_cipher_by_port(cls, port) -> CipherMan:
        user_list = User.list_by_port(port)
        if len(user_list) == 1:
            access_user = user_list[0]
        else:
            access_user = None
        return cls(user_list, access_user=access_user)

    @FIND_ACCESS_USER_TIME.time()
    def _find_access_user(self, first_data: bytes) -> User:
        """通过auth校验来找到正确的user"""

        with memoryview(first_data) as d:
            salt = first_data[: self.cipher_cls.SALT_SIZE]
            if salt in self.bf:
                raise RuntimeError("repeated salt founded!")
            else:
                self.bf.add(salt)

        t1 = time.time()
        success_user = None
        cnt = 0
        for user in self.user_list:
            if not self.last_access_user:
                self.last_access_user = user
            cipher = self.cipher_cls(user.password)
            try:
                cnt += 1
                with memoryview(first_data) as d:
                    cipher.decrypt(d)
                success_user = user
                break
            except ValueError as e:
                if e.args[0] != "MAC check failed":
                    raise e
                del cipher
        logging.info(
            f"用户:{success_user} 一共寻找了{ cnt }个user,共花费{(time.time()-t1)*1000}ms"
        )
        return success_user

    def _init_cipher(self, data):
        if len(data) + len(self._buffer) < self._first_data_len:
            self._buffer.extend(data)
            return
        else:
            data = bytes(self._buffer) + data
            del self._buffer[:]
        if not self.access_user:
            self.access_user = self._find_access_user(data)

        if not self.access_user:
            raise RuntimeError("没有找到合法的用户")
        if not self.access_user.enable:
            raise RuntimeError(f"用户: {self.access_user} enable = False")

        if (
            self.access_user
            and self.last_access_user
            and self.access_user != self.last_access_user
        ):
            self.access_user.access_order = self.user_list.first().access_order + 1
            self.access_user.save()

        self.cipher = self.cipher_cls(self.access_user.password)

        return data

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
            data = self._init_cipher(data)
        if not data:
            return
        self.access_user and self.access_user.record_traffic(len(data), len(data))
        NETWORK_TRANSMIT_BYTES.inc(len(data))
        return self.cipher.decrypt(data)

    def incr_user_tcp_num(self, num: int):
        self.access_user and self.access_user.incr_tcp_conn_num(num)

    def record_user_ip(self, peername):
        self.access_user and self.access_user.record_ip(peername)
