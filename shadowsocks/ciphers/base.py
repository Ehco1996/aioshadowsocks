import abc
import hashlib
import hmac
import os
import sys

from shadowsocks.ciphers.utils import evp_bytestokey

from Crypto.Cipher import AES


class BaseCipher(metaclass=abc.ABCMeta):
    KEY_SIZE = -1
    SALT_SIZE = -1
    NONCE_SIZE = -1
    TAG_SIZE = -1

    def __init__(self, password: str):
        self.key = evp_bytestokey(password.encode(), self.KEY_SIZE)

    @abc.abstractmethod
    def new_cipher(self, *arg, **kwargs):
        return


class BaseStreamCipher(BaseCipher, metaclass=abc.ABCMeta):
    """Shadowsocks Stream cipher
    spec: https://shadowsocks.org/en/spec/Stream-Ciphers.html
    """

    IV_SIZE = 0

    def make_random_iv(self):
        return os.urandom(self.IV_SIZE)

    @abc.abstractmethod
    def new_cipher(self, key: bytes, iv: bytes):
        return

    def init_encrypt_func(self):
        cipher = self.new_cipher(self.key, self.make_random_iv())

        def encrypt(plaintext: bytes) -> bytes:
            return cipher.encrypt(plaintext)

        return encrypt

    def init_decrypt_func(self, iv: bytes):
        cipher = self.new_cipher(self.key, iv)

        def decrypt(ciphertext: bytes) -> bytes:
            return cipher.decrypt(ciphertext)

        return decrypt


class AESCipher(BaseStreamCipher):
    def new_cipher(self, key: bytes, iv: bytes):
        return AES.new(key, mode=AES.MODE_CFB, iv=iv, segment_size=128)


class AES256CFB(AESCipher):
    METHOD = "aes-256-cfb"
    KEY_SIZE = 32
    IV_SIZE = 16
