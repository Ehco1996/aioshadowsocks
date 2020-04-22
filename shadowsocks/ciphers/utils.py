import hashlib


def evp_bytestokey(password: bytes, key_size: int):
    """
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
