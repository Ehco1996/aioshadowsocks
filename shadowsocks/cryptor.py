from shadowsocks.ciphers.aes import AESCipher
from shadowsocks.ciphers.none import NONECipher
from shadowsocks.metrics import ENCRYPT_DATA_TIME, DECRYPT_DATA_TIME


class Cryptor:

    # 注册所有加密方式
    SUPPORT_METHODS = {}

    def __init__(self, method, password, flag):
        self._crypto = None
        self._register_chipher()

        # 找到指定的cipher
        for name, methods in self.SUPPORT_METHODS.items():
            if method in methods:
                if name == "aes":
                    self._crypto = AESCipher(method, password, flag)
                elif name == "none":
                    self._crypto = NONECipher(method, password, flag)

        if self._crypto is None:
            raise NotImplementedError

    def _register_chipher(self):
        """注册所有的chiper"""
        # aes
        self.SUPPORT_METHODS["aes"] = AESCipher.SUPPORT_METHODS
        # none
        self.SUPPORT_METHODS["none"] = NONECipher.SUPPORT_METHODS

    @ENCRYPT_DATA_TIME.time()
    def encrypt(self, data):
        t1 = time.time()
        return self._crypto.encrypt(data)

    @DECRYPT_DATA_TIME.time()
    def decrypt(self, data):
        return self._crypto.decrypt(data)
