import abc
import hashlib
import os

import hkdf
from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305


def evp_bytestokey(password: bytes, key_size: int):
    """make user password stronger
    openssl EVP_BytesToKey python implement
    doc: https://www.openssl.org/docs/manmaster/man3/EVP_BytesToKey.html
    """
    m = []
    for i in range(key_size // 16):
        data = m[i - 1] + password if i > 0 else password
        md5 = hashlib.md5()
        md5.update(data)
        m.append(md5.digest())
    return b"".join(m)


class BaseCipher(metaclass=abc.ABCMeta):
    KEY_SIZE = -1
    AEAD_CIPHER = False

    def __init__(self, password: str):
        self.key = evp_bytestokey(password.encode(), self.KEY_SIZE)

    @abc.abstractmethod
    def new_cipher(self, *arg, **kwargs):
        return

    @abc.abstractmethod
    def encrypt(self, data: bytes):
        return

    @abc.abstractmethod
    def decrypt(self, data: bytes):
        return

    @abc.abstractmethod
    def unpack(self, data: bytes) -> bytes:
        return

    @abc.abstractmethod
    def pack(self, data: bytes) -> bytes:
        return


class BaseAEADCipher(BaseCipher):
    """DOC: https://shadowsocks.org/en/wiki/AEAD-Ciphers
    TCP: [encrypted payload length][length tag][encrypted payload][payload tag]
    UDP: [salt][encrypted payload][tag]
    """

    INFO = b"ss-subkey"
    PACKET_LIMIT = 16 * 1024 - 1
    SALT_SIZE = -1
    NONCE_SIZE = -1
    TAG_SIZE = -1
    AEAD_CIPHER = True

    def __init__(self, password: str):
        super().__init__(password)
        self._buffer = bytearray()
        self._payload_len = None
        self._subkey = None
        self._counter = 0
        self._cipher = None

    def _derive_subkey(self, salt: bytes):
        return hkdf.Hkdf(salt, self.key, hashlib.sha1).expand(self.INFO, self.KEY_SIZE)

    def _make_random_salt(self):
        return os.urandom(self.SALT_SIZE)

    def _encrypt(self, plaintext: bytes):
        if not self._cipher:
            self._cipher = self.new_cipher(self._subkey)
        return self._cipher.encrypt(self.nonce, plaintext, None)

    def _decrypt(self, ciphertext: bytes, tag: bytes):
        if not self._cipher:
            self._cipher = self.new_cipher(self._subkey)
        return self._cipher.decrypt(self.nonce, bytes(ciphertext + tag), None)

    @property
    def nonce(self):
        ret = self._counter.to_bytes(self.NONCE_SIZE, "little")
        self._counter += 1
        return ret

    def encrypt(self, data: bytes) -> bytes:
        ret = bytearray()
        if self._subkey is None:
            salt = self._make_random_salt()
            self._subkey = self._derive_subkey(salt)
            ret.extend(salt)
        for i in range(0, len(data), self.PACKET_LIMIT):
            buf = data[i : i + self.PACKET_LIMIT]
            #  len_chunk, len_tag  + body_chunk + body_tag
            ret.extend(self._encrypt(len(buf).to_bytes(2, "big")) + self._encrypt(buf))
        return bytes(ret)

    def decrypt(self, data: bytes) -> bytes:
        ret = bytearray()
        if self._subkey is None:
            salt, data = data[: self.SALT_SIZE], data[self.SALT_SIZE :]
            self._subkey = self._derive_subkey(salt)

        self._buffer.extend(data)

        while True:
            if not self._payload_len:
                # 从data里拿出payload_length
                if len(self._buffer) < 2 + self.TAG_SIZE:
                    break
                self._payload_len = int.from_bytes(
                    self._decrypt(
                        self._buffer[:2], self._buffer[2 : 2 + self.TAG_SIZE]
                    ),
                    "big",
                )
                if self._payload_len > self.PACKET_LIMIT:
                    raise RuntimeError(f"payload_len too long {self._payload_len}")

                del self._buffer[: 2 + self.TAG_SIZE]
            else:
                if len(self._buffer) < self._payload_len + self.TAG_SIZE:
                    break
                ret.extend(
                    self._decrypt(
                        self._buffer[: self._payload_len],
                        self._buffer[
                            self._payload_len : self._payload_len + self.TAG_SIZE
                        ],
                    )
                )
                del self._buffer[: self._payload_len + self.TAG_SIZE]
                self._payload_len = None

        return bytes(ret)

    def unpack(self, data: bytes) -> bytes:
        """解包udp"""
        ret = bytearray()
        data_len = len(data)
        salt, data, tag = (
            data[: self.SALT_SIZE],
            data[self.SALT_SIZE : data_len - self.TAG_SIZE],
            data[data_len - self.TAG_SIZE :],
        )
        self._subkey = self._derive_subkey(salt)
        ret.extend(self._decrypt(data, tag))
        return bytes(ret)

    def pack(self, data: bytes) -> bytes:
        """压udp包"""
        ret = bytearray()
        salt = self._make_random_salt()
        self._subkey = self._derive_subkey(salt)
        ret.extend(salt)
        ret.extend(self._encrypt(data))
        return bytes(ret)

    @classmethod
    def tcp_first_data_len(cls):
        return cls.SALT_SIZE + 2 + cls.TAG_SIZE


class NONE(BaseCipher):
    def new_cipher(self, key: bytes, iv: bytes):
        return

    def encrypt(self, data: bytes):
        return data

    def decrypt(self, data: bytes):
        return data

    def unpack(self, data: bytes) -> bytes:
        return data

    def pack(self, data: bytes) -> bytes:
        return data


class CHACHA20IETFPOLY1305(BaseAEADCipher):
    KEY_SIZE = 32
    SALT_SIZE = 32
    NONCE_SIZE = 12
    TAG_SIZE = 16

    def new_cipher(self, subkey: bytes):
        return ChaCha20Poly1305(key=subkey)


class AES128GCM(BaseAEADCipher):
    KEY_SIZE = 16
    SALT_SIZE = 16
    NONCE_SIZE = 12
    TAG_SIZE = 16

    def new_cipher(self, subkey: bytes):
        return AESGCM(subkey)


class AES256GCM(AES128GCM):
    KEY_SIZE = 32
    SALT_SIZE = 32
    NONCE_SIZE = 12
    TAG_SIZE = 16


# NOTE 目前提供所有AEAD的加密方式，流式加密只提供None（不加密）
# 但是所有流式加密的方式都不推荐使用了，生产环境请一律使用AEAD加密
SUPPORT_METHODS = {
    "none": NONE,
    "aes-128-gcm": AES128GCM,
    "aes-256-gcm": AES256GCM,
    "chacha20-ietf-poly1305": CHACHA20IETFPOLY1305,
}
