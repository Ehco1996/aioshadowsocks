from __future__ import annotations

from logging import fatal

from shadowsocks import protocol_flag as flag
from shadowsocks.ciphers import (AES128GCM, AES256CFB, AES256GCM,
                                 CHACHA20IETFPOLY1305, NONE)
from shadowsocks.mdb.models import User
from shadowsocks.metrics import (DECRYPT_DATA_TIME, ENCRYPT_DATA_TIME,
                                 NETWORK_TRANSMIT_BYTES)
from shadowsocks.utils import AutoResetBloomFilter


class CipherMan:

    SUPPORT_METHODS = {
        "none": NONE,
        "aes-256-cfb": AES256CFB,
        "aes-128-gcm": AES128GCM,
        "aes-256-gcm": AES256GCM,
        "chacha20-ietf-poly1305": CHACHA20IETFPOLY1305,
    }
    bf = AutoResetBloomFilter()

    # TODO 流量、链接数限速

    def __init__(
        self,
        user_port=None,
        access_user: User = None,
        ts_protocol=flag.TRANSPORT_TCP,
    ):
        self.user_port = user_port
        self.access_user = access_user
        self.ts_protocol = ts_protocol

        self.cipher = None
        self._buffer = bytearray()
        self.last_access_user = None

        if self.access_user:
            self.method = access_user.method
        else:
            self.method = (
                User.list_by_port(self.user_port).first().method
            )  # NOTE 所有的user用的加密方式必须是一种

        self.cipher_cls = self.SUPPORT_METHODS.get(self.method)
        if self.cipher_cls.AEAD_CIPHER and self.ts_protocol == flag.TRANSPORT_TCP:
            self._first_data_len = self.cipher_cls.tcp_first_data_len()
        else:
            self._first_data_len = 0

    @classmethod
    def get_cipher_by_port(cls, port, ts_protocol) -> CipherMan:
        user_query = User.list_by_port(port)
        if user_query.count() == 1:
            access_user = user_query.first()
        else:
            access_user = None
        return cls(port, access_user=access_user, ts_protocol=ts_protocol)

    @ENCRYPT_DATA_TIME.time()
    def encrypt(self, data: bytes):
        self.record_user_traffic(0, len(data))

        if self.ts_protocol == flag.TRANSPORT_UDP:
            cipher = self.cipher_cls(self.access_user.password)
            return cipher.pack(data)

        if not self.cipher:
            self.cipher = self.cipher_cls(self.access_user.password)
        return self.cipher.encrypt(data)

    @DECRYPT_DATA_TIME.time()
    def decrypt(self, data: bytes):
        if (
            self.access_user is None
            and len(data) + len(self._buffer) < self._first_data_len
        ):
            self._buffer.extend(data)
            return

        if not self.access_user:
            self._buffer.extend(data)
            if self.ts_protocol == flag.TRANSPORT_TCP:
                first_data, self._buffer = (
                    self._buffer[: self._first_data_len],
                    self._buffer[self._first_data_len :],
                )
            else:
                first_data = self._buffer
            salt = first_data[: self.cipher_cls.SALT_SIZE]
            if salt in self.bf:
                raise RuntimeError("repeated salt founded!")
            else:
                self.bf.add(salt)

            self.access_user, self.cipher = User.find_access_user_and_cipher_by_data(
                self.user_port, self.cipher_cls, self.ts_protocol, first_data
            )
            data = bytes(self._buffer)

        self.record_user_traffic(len(data), 0)
        if self.ts_protocol == flag.TRANSPORT_TCP:
            return self.cipher.decrypt(data)
        else:
            return self.cipher_cls(self.access_user.password).unpack(data)

    def incr_user_tcp_num(self, num: int):
        self.access_user and self.access_user.incr_tcp_conn_num(num)

    def record_user_ip(self, peername):
        self.access_user and self.access_user.record_ip(peername)

    def record_user_traffic(self, ut_data_len: int, dt_data_len: int):
        self.access_user and self.access_user.record_traffic(ut_data_len, dt_data_len)
        NETWORK_TRANSMIT_BYTES.inc(ut_data_len + dt_data_len)
