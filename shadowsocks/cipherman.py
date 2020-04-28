from shadowsocks.ciphers import AES256CFB, NONE, ChaCha20IETFPoly1305
from shadowsocks.mdb.models import User


class CipherMan:

    SUPPORT_METHODS = {
        "aes-256-cfb": AES256CFB,
        "none": NONE,
        "chacha20-ietf-poly1305": ChaCha20IETFPoly1305,
    }

    @classmethod
    def get_cipher_by_port(cls, port) -> CipherMan:
        return

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
