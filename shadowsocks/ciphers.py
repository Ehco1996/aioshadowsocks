import abc
import hashlib
import os
import logging

import hkdf
from Crypto.Cipher import AES, ChaCha20_Poly1305

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

    def __init__(self, password: str):
        self.key = evp_bytestokey(password.encode(), self.KEY_SIZE)

    @abc.abstractmethod
    def new_cipher(self, *arg, **kwargs):
        return


class BaseStreamCipher(BaseCipher, metaclass=abc.ABCMeta):
    """Shadowsocks Stream cipher
    spec: https://shadowsocks.org/en/spec/Stream-Ciphers.html
    """

    AEAD_CIPHER = False
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


class BaseAEADCipher(BaseCipher):
    AEAD_CIPHER = True
    INFO = b"ss-subkey"
    PACKET_LIMIT = 0x3FF

    SALT_SIZE = -1
    NONCE_SIZE = -1
    TAG_SIZE = -1

    def _derive_subkey(self, salt: bytes):
        return hkdf.Hkdf(salt, self.key, hashlib.sha1).expand(self.INFO, self.KEY_SIZE)

    def make_random_salt(self):
        return os.urandom(self.SALT_SIZE)

    def init_encrypt_func(self, salt: bytes):
        counter = 0
        salt = salt if salt is not None else self.make_random_salt()
        subkey = self._derive_subkey(salt)

        def encrypt(plaintext: bytes):
            nonlocal counter
            nonce = counter.to_bytes(self.NONCE_SIZE, "little")
            counter += 1
            cipher = self.new_cipher(subkey, nonce)
            if len(plaintext) <= self.PACKET_LIMIT:
                return cipher.encrypt_and_digest(plaintext)
            else:
                with memoryview(plaintext) as data:
                    # 分包发出去
                    return cipher.encrypt_and_digest(
                        data[: self.PACKET_LIMIT]
                    ) + encrypt(data[self.PACKET_LIMIT :])

        return salt, encrypt

    def init_decrypt_func(self, salt: bytes):
        counter = 0
        subkey = self._derive_subkey(salt)

        def decrypt(ciphertext: bytes, tag: bytes):
            nonlocal counter
            nonce = counter.to_bytes(self.NONCE_SIZE, "little")
            counter += 1
            cipher = self.new_cipher(subkey, nonce)
            return cipher.decrypt_and_verify(ciphertext, tag)

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
    KEY_SIZE = 32
    IV_SIZE = 16


class ChaCha20IETFPoly1305(BaseAEADCipher):
    KEY_SIZE = 32
    SALT_SIZE = 32
    NONCE_SIZE = 12
    TAG_SIZE = 16

    def new_cipher(self, subkey: bytes, nonce: bytes):
        return ChaCha20_Poly1305.new(key=subkey, nonce=nonce)


class CipherMan:

    SUPPORT_METHODS = {
        "aes-256-cfb": AES256CFB,
        "none": NONE,
        "chacha20-ietf-poly1305": ChaCha20IETFPoly1305,
    }

    def __init__(self, method, password):
        self.cipher_cls = self.SUPPORT_METHODS.get(method)
        self.cipher = self.cipher_cls(password)

        self.encrypt_func = None
        self.decrypt_func = None

    def stream_encrypt(self, data: bytes):
        if not self.encrypt_func:
            self.encrypt_func = self.cipher.init_encrypt_func()
        return self.encrypt_func(data)

    def stream_decrypt(self, data: bytes):
        if not self.decrypt_func:
            iv, data = data[: self.cipher_cls.IV_SIZE], data[self.cipher_cls.IV_SIZE :]
            self.decrypt_func = self.cipher.init_decrypt_func(iv)
        return self.decrypt_func(data)

    def aead_encrypt(self, data: bytes):
        packet = b""
        if not self.encrypt_func:
            salt, self.encrypt_func = self.cipher.init_encrypt_func(None)
            packet += salt
        length = len(data)
        packet += b"".join(self.encrypt_func(length.to_bytes(2, "big")))
        packet += b"".join(self.encrypt_func(data))
        return packet

    def aead_decrypt(self, data: bytes):
        if not data:
            return b""

        salt_size = self.cipher_cls.SALT_SIZE
        tag_size = self.cipher_cls.TAG_SIZE

        if not self.decrypt_func:
            salt, data = data[:salt_size], data[salt_size:]
            self.decrypt_func = self.cipher.init_decrypt_func(salt)

        # first chunk(payload length)
        chunk0, data = data[: 2 + tag_size], data[2 + tag_size :]
        with memoryview(chunk0) as chunk:
            length = self.decrypt_func(chunk[:2], chunk[2:])
        length = int.from_bytes(length, "big")
        if length != length & BaseAEADCipher.PACKET_LIMIT:
            raise Exception("length too long !")

        # decrypt payload
        chunk, data = data[: length + tag_size], data[length + tag_size :]
        with memoryview(chunk) as d:
            payload = self.decrypt_func(d[:length], d[length:])
        return payload + self.aead_decrypt(data)

    @ENCRYPT_DATA_TIME.time()
    def encrypt(self, data: bytes):
        if self.cipher_cls.AEAD_CIPHER:
            return self.aead_encrypt(data)
        return self.stream_encrypt(data)

    @DECRYPT_DATA_TIME.time()
    def decrypt(self, data: bytes):
        if self.cipher_cls.AEAD_CIPHER:
            return self.aead_decrypt(data)
        return self.stream_decrypt(data)
