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

    def __init__(self, password: str):
        super().__init__(password)

        self.encrypt_func = None
        self.decrypt_func = None

    def make_random_iv(self):
        return os.urandom(self.IV_SIZE)

    @abc.abstractmethod
    def new_cipher(self, key: bytes, iv: bytes):
        return

    def _init_encrypt_func(self):
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

    def _init_decrypt_func(self, iv: bytes):
        cipher = self.new_cipher(self.key, iv)

        def decrypt(ciphertext: bytes) -> bytes:
            return cipher.decrypt(ciphertext)

        return decrypt

    def encrypt(self, data: bytes):
        if not self.encrypt_func:
            self.encrypt_func = self._init_encrypt_func()
        return self.encrypt_func(data)

    def decrypt(self, data: bytes):
        if not self.decrypt_func:
            iv, data = data[: self.IV_SIZE], data[self.IV_SIZE :]
            self.decrypt_func = self._init_decrypt_func(iv)
        return self.decrypt_func(data)


class BaseAEADCipher(BaseCipher):
    INFO = b"ss-subkey"
    PACKET_LIMIT = 16 * 1024 - 1
    SALT_SIZE = -1
    NONCE_SIZE = -1
    TAG_SIZE = -1

    def __init__(self, password: str):
        super().__init__(password)
        self._buffer = bytearray()
        self._payload_len = None

        self.encrypt_func = None
        self.decrypt_func = None

    def _derive_subkey(self, salt: bytes):
        return hkdf.Hkdf(salt, self.key, hashlib.sha1).expand(self.INFO, self.KEY_SIZE)

    def _make_random_salt(self):
        return os.urandom(self.SALT_SIZE)

    def _init_encrypt_func(self, salt: bytes):
        counter = 0
        salt = salt if salt is not None else self._make_random_salt()
        subkey = self._derive_subkey(salt)

        def encrypt(plaintext: bytes):
            nonlocal counter
            nonce = counter.to_bytes(self.NONCE_SIZE, "little")
            counter += 1
            cipher = self.new_cipher(subkey, nonce)
            return cipher.encrypt_and_digest(plaintext)

        return salt, encrypt

    def _init_decrypt_func(self, salt: bytes):
        counter = 0
        subkey = self._derive_subkey(salt)

        def decrypt(ciphertext: bytes, tag: bytes):
            nonlocal counter
            nonce = counter.to_bytes(self.NONCE_SIZE, "little")
            counter += 1
            cipher = self.new_cipher(subkey, nonce)
            return cipher.decrypt_and_verify(ciphertext, tag)

        return decrypt

    def encrypt(self, data: bytes):
        ret = bytearray()
        if not self.encrypt_func:
            salt, self.encrypt_func = self._init_encrypt_func(None)
            ret.extend(salt)

        for i in range(0, len(data), self.PACKET_LIMIT):
            buf = data[i : i + self.PACKET_LIMIT]
            len_chunk, len_tag = self.encrypt_func(len(buf).to_bytes(2, "big"))
            body_chunk, body_tag = self.encrypt_func(buf)
            ret.extend(len_chunk + len_tag + body_chunk + body_tag)

        return bytes(ret)

    def decrypt(self, data: bytes):
        ret = bytearray()
        if not self.decrypt_func:
            salt, data = data[: self.SALT_SIZE], data[self.SALT_SIZE :]
            self.decrypt_func = self._init_decrypt_func(salt)

        self._buffer.extend(data)

        while True:
            if not self._payload_len:
                # 从data里拿出payload_length
                if len(self._buffer) < 2 + self.TAG_SIZE:
                    break
                else:
                    self._payload_len = int.from_bytes(
                        self.decrypt_func(
                            self._buffer[:2], self._buffer[2 : 2 + self.TAG_SIZE]
                        ),
                        "big",
                    )
                    assert self._payload_len < self.PACKET_LIMIT
                    del self._buffer[: 2 + self.TAG_SIZE]
            else:
                if len(self._buffer) < self._payload_len + self.TAG_SIZE:
                    break
                ret.extend(
                    self.decrypt_func(
                        self._buffer[: self._payload_len],
                        self._buffer[
                            self._payload_len : self._payload_len + self.TAG_SIZE
                        ],
                    )
                )
                del self._buffer[: self._payload_len + self.TAG_SIZE]
                self._payload_len = None

        return bytes(ret)


class AESCipher(BaseStreamCipher):
    def new_cipher(self, key: bytes, iv: bytes):
        return AES.new(key, mode=AES.MODE_CFB, iv=iv, segment_size=128)


class NONE(BaseStreamCipher):
    def new_cipher(self, key: bytes, iv: bytes):
        return

    def _init_encrypt_func(self):
        def encrypt(plaintext: bytes) -> bytes:
            return plaintext

        return encrypt

    def _init_decrypt_func(self, iv: bytes):
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

    @ENCRYPT_DATA_TIME.time()
    def encrypt(self, data: bytes):
        return self.cipher.encrypt(data)

    @DECRYPT_DATA_TIME.time()
    def decrypt(self, data: bytes):
        return self.cipher.decrypt(data)
