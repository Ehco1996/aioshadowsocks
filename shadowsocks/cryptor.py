from shadowsocks.ciphers.base import AES256CFB
from shadowsocks.metrics import ENCRYPT_DATA_TIME, DECRYPT_DATA_TIME


SUPPORT_METHODS = {"aes-256-cfb": AES256CFB}


class Cryptor:

    # 注册所有加密方式

    def __init__(self, method, password):
        self.cipher_cls = SUPPORT_METHODS.get(method)
        self.cipher = self.cipher_cls(password)

        self.encrypt_func = None
        self.decrypt_func = None

    @ENCRYPT_DATA_TIME.time()
    def encrypt(self, data: bytes):
        if not self.encrypt_func:
            self.encrypt_func = self.cipher.init_encrypt_func()
        return self.encrypt_func(data)

    @DECRYPT_DATA_TIME.time()
    def decrypt(self, data: bytes):
        if not self.decrypt_func:
            iv, data = data[: self.cipher_cls.IV_SIZE], data[self.cipher_cls.IV_SIZE :]
            self.decrypt_func = self.cipher.init_decrypt_func(iv)
        return self.decrypt_func(data)
