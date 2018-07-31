import pytest

from shadowsocks.crypto.aes import AESCipher


def test_aes_crypto(crypto_data):
    '''测试aes系列加密解密'''

    for method in AESCipher.SUPPORT_METHODS:
        cryptor = AESCipher(method, 'passwd')
        for data in crypto_data:
            ct = cryptor.encrypt(data)
            et = cryptor.decrypt(ct)
            assert et == data
