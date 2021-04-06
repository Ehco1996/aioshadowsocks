import os
import time

from shadowsocks.ciphers import SUPPORT_METHODS


def _test_cipher(cipher_cls, size=32 * 1024, repeat=128):
    password = "i am password"
    for _ in range(repeat):
        enc = cipher_cls(password)

        plain_text = os.urandom(size)
        enc_text = enc.encrypt(plain_text)

        dep = cipher_cls(password)
        dep_text = dep.decrypt(enc_text)

        assert dep_text == plain_text


def test_cipher():
    for _, cipher_cls in SUPPORT_METHODS.items():
        t = time.perf_counter()
        _test_cipher(cipher_cls, size=256000)
        print(cipher_cls, time.perf_counter() - t)
