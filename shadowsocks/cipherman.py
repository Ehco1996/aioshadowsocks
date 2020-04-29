from __future__ import annotations

from shadowsocks.ciphers import AES256CFB, NONE, ChaCha20IETFPoly1305
from shadowsocks.mdb.models import User
from shadowsocks.metrics import DECRYPT_DATA_TIME, ENCRYPT_DATA_TIME


class CipherMan:

    SUPPORT_METHODS = {
        "aes-256-cfb": AES256CFB,
        "none": NONE,
        "chacha20-ietf-poly1305": ChaCha20IETFPoly1305,
    }

    @classmethod
    def get_cipher_by_port(cls, port) -> CipherMan:
        user_list = User.list_by_port(port)
        if len(user_list) != 1:
            raise ValueError("单个端口找到了多个用户")
        return cls(user_list[0])

    def __init__(self, user: User):
        self.cipher_cls = self.SUPPORT_METHODS.get(user.method)
        self.method = user.method
        self.password = user.password
        self.cipher = self.cipher_cls(user.password)
        self.user = user

    @ENCRYPT_DATA_TIME.time()
    def encrypt(self, data: bytes):
        return self.cipher.encrypt(data)

    @DECRYPT_DATA_TIME.time()
    def decrypt(self, data: bytes):
        return self.cipher.decrypt(data)
