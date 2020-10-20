import os
import time

from shadowsocks.ciphers import SUPPORT_METHODS


def test_cipher(cipher_cls, size=32 * 1024, repeat=128):
    for i in range(repeat):
        password = "i am password"
        enc = cipher_cls(password)

        plain_text = os.urandom(size)
        enc_text = enc.encrypt(plain_text)

        dep = cipher_cls(password)
        dep_text = dep.decrypt(enc_text)

        assert dep_text == plain_text


if __name__ == "__main__":
    for key, cipher_cls in SUPPORT_METHODS.items():
        t = time.perf_counter()
        test_cipher(cipher_cls, size=256000)
        print(cipher_cls, time.perf_counter() - t)
