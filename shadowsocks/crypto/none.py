'''
提供AES系列加密解密
'''
import os

from shadowsocks.crypto.utils import evp_bytestokey


class NONECipher:
    SUPPORT_METHODS = {
        'none': -1,
    }

    def __init__(self, method, password, flag):
        self._method = method
        self._password = password
        self._flag = flag

    def encrypt(self, data):
        return data

    def decrypt(self, data):
        return data
