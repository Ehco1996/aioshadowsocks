import abc
import hashlib
import os

from Crypto.Cipher import AES

from shadowsocks.ciphers.base import AES256CFB, NONE
from shadowsocks.metrics import DECRYPT_DATA_TIME, ENCRYPT_DATA_TIME


def evp_bytestokey(password: bytes, key_size: int):
    """make user password stronger
    openssl EVP_BytesToKey python implement
    doc: https://www.openssl.org/docs/manmaster/man3/EVP_BytesToKey.html
    """
    m = []
    for i in range(key_size // 16):
        if i > 0:
            data = m[i - 1] + password
        else:
            data = password
        md5 = hashlib.md5()
        md5.update(data)
        m.append(md5.digest())
    return b"".join(m)


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
        first_package = True
        iv = self.make_random_iv()
        cipher = self.new_cipher(self.key, iv)

        def encrypt(plaintext: bytes) -> bytes:
            nonlocal first_package
            ciphertext = cipher.encrypt(plaintext)
            if first_package:
                first_package = False
                return iv + ciphertext
            return ciphertext

        return encrypt

    def init_decrypt_func(self, iv: bytes):
        cipher = self.new_cipher(self.key, iv)

        def decrypt(ciphertext: bytes) -> bytes:
            return cipher.decrypt(ciphertext)

        return decrypt


class AESCipher(BaseStreamCipher):
    def new_cipher(self, key: bytes, iv: bytes):
        return AES.new(key, mode=AES.MODE_CFB, iv=iv, segment_size=128)


class NONE(BaseStreamCipher):
    def new_cipher(self, key: bytes, iv: bytes):
        return

    def init_encrypt_func(self):
        def encrypt(plaintext: bytes) -> bytes:
            return plaintext

        return encrypt

    def init_decrypt_func(self, iv: bytes):
        def decrypt(ciphertext: bytes) -> bytes:
            return ciphertext

        return decrypt


class AES256CFB(AESCipher):
    METHOD = "aes-256-cfb"
    KEY_SIZE = 32
    IV_SIZE = 16


class CipherMan:

    SUPPORT_METHODS = {"aes-256-cfb": AES256CFB, "none": NONE}

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
