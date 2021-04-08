from __future__ import annotations

from shadowsocks import protocol_flag as flag
from shadowsocks.ciphers import SUPPORT_METHODS
from shadowsocks.mdb.models import User
from shadowsocks.metrics import (
    DECRYPT_DATA_TIME,
    ENCRYPT_DATA_TIME,
    NETWORK_TRANSMIT_BYTES,
)


class CipherMan:
    # TODO 流量、链接数限速

    def __init__(
        self,
        method=None,
        user_port=None,
        peername=None,
        access_user: User = None,
        ts_protocol=flag.TRANSPORT_TCP,
    ):
        self.method = method
        self.peername = peername
        self.user_port = user_port
        self.access_user = access_user
        self.ts_protocol = ts_protocol
        self.cipher_cls = SUPPORT_METHODS.get(self.method)
        if not self.cipher_cls:
            raise Exception(f"暂时不支持这种加密方式:{self.method}")

        if ts_protocol == flag.TRANSPORT_TCP:
            self._first_data_len = self.cipher_cls.tcp_first_data_len()
        else:
            self._first_data_len = 0
        self.cipher = None
        self._buffer = bytearray()

    @classmethod
    async def get_cipher_by_port(
        cls, port, ts_protocol, peername, access_user=None
    ) -> CipherMan:
        if access_user:
            method = access_user.method
        else:
            same_port_users = User.list_by_port(port)
            first_user = await same_port_users.first()
            # NOTE 单端口多用户所有的user用的加密方式必须是一种
            method = first_user.method
            if await same_port_users.count() == 1:
                access_user = first_user
        return cls(
            method=method,
            user_port=port,
            peername=peername,
            access_user=access_user,
            ts_protocol=ts_protocol,
        )

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
    async def decrypt(self, data: bytes):
        if (
            self.access_user is None
            and len(data) + len(self._buffer) < self._first_data_len
        ):
            self._buffer.extend(data)
            return

        if not self.access_user:
            self._buffer.extend(data)
            if self.ts_protocol == flag.TRANSPORT_TCP:
                first_data = self._buffer[: self._first_data_len]
            else:
                first_data = self._buffer
            access_user = await User.find_access_user(
                self.user_port,
                self.method,
                self.ts_protocol,
                first_data,
            )

            if not access_user:
                raise RuntimeError(
                    f"can not find enable access user: {self.user_port}-{self.ts_protocol}-{self.cipher_cls}"
                )
            if not access_user.enable:
                raise RuntimeError(f"access user not have traffic: {access_user}")
            self.access_user = access_user
            self.record_user_ip(self.peername)
            self.incr_user_tcp_num(1)
            data = bytes(self._buffer)
        if not self.cipher:
            self.cipher = self.cipher_cls(self.access_user.password)

        self.record_user_traffic(len(data), 0)
        if self.ts_protocol == flag.TRANSPORT_TCP:
            return self.cipher.decrypt(data)
        else:
            return self.cipher_cls(self.access_user.password).unpack(data)

    def incr_user_tcp_num(self, num: int):
        self.ts_protocol == flag.TRANSPORT_TCP and self.access_user and self.access_user.incr_tcp_conn_num(
            num
        )

    def record_user_ip(self, peername):
        self.access_user and self.access_user.record_ip(peername)

    def record_user_traffic(self, ut_data_len: int, dt_data_len: int):
        self.access_user and self.access_user.record_traffic(ut_data_len, dt_data_len)
        NETWORK_TRANSMIT_BYTES.inc(ut_data_len + dt_data_len)

    def close(self):
        self.incr_user_tcp_num(-1)
