import pytest

from shadowsocks.cryptor import Cryptor
from shadowsocks.crypto.aes import AESCipher


def test_aes_crypto(crypto_data):
    '''测试aes系列加密解密'''

    for method in AESCipher.SUPPORT_METHODS:
        cryptor = AESCipher(method, 'passwd')
        for data in crypto_data:
            ct = cryptor.encrypt(data)
            et = cryptor.decrypt(ct)
            assert et == data


def test_find_cipher(crypto_data, support_methods):
    '''测试找到合适的cipher'''

    for method in support_methods:
        cryptor = Cryptor(method, 'passwd')
        for data in crypto_data:
            assert cryptor.decrypt(cryptor.encrypt(data)) == data
