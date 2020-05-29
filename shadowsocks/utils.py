import logging
import re
import socket
import struct
import time
from functools import lru_cache

from bloom_filter import BloomFilter

from shadowsocks import protocol_flag as flag


def is_stream_domain(domain):
    # 目前只匹配 netflix、hulu、HBO
    if STREAM_HOST_PATTERN.search(domain):
        return True
    return False


def logging_cahce_info():
    def wrapper(func):
        def decorated(*args, **kwargs):
            logging.debug(f"domain:{args[0]} cache_info: {func.cache_info()}")
            return func(*args, **kwargs)

        return decorated

    return wrapper


@logging_cahce_info()
@lru_cache(2 ** 8)
def get_ip_from_domain(domain):
    try:
        return socket.gethostbyname(domain.encode())
    except Exception:
        logging.warning(f"Failed to query DNS: {domain}")
        return domain


def parse_header(data):
    # shadowsocks protocol https://shadowsocks.org/en/spec/Protocol.html
    atype, dst_addr, dst_port, header_length = data[0], None, None, 0
    if atype == flag.ATYPE_IPV4:
        if len(data) >= 7:
            dst_addr = socket.inet_ntop(socket.AF_INET, data[1:5])
            dst_port = struct.unpack("!H", data[5:7])[0]
            header_length = 7
        else:
            logging.warning("header is too short")
    elif atype == flag.ATYPE_IPV6:
        if len(data) >= 19:
            dst_addr = socket.inet_ntop(socket.AF_INET6, data[1:17])
            dst_port = struct.unpack("!H", data[17:19])[0]
            header_length = 19
        else:
            logging.warning("header is too short")
    elif atype == flag.ATYPE_DOMAINNAME:
        if len(data) > 2:
            addrlen = data[1]
            if len(data) >= 4 + addrlen:
                dst_addr = data[2 : 2 + addrlen]
                dst_addr = get_ip_from_domain(dst_addr.decode())
                dst_port = struct.unpack("!H", data[2 + addrlen : addrlen + 4])[0]
                header_length = 4 + addrlen
            else:
                logging.warning("header is too short")
        else:
            logging.warning("header is too short")
    else:
        logging.warning(f"unknown atype: {atype}")

    return atype, dst_addr, dst_port, header_length


class AutoResetBloomFilter:

    MAX_ELEMENTS = 10 ** 6
    ERROR_RATE = 10 ** -6

    def new_bf(self):
        self.size = self.MAX_ELEMENTS
        return BloomFilter(max_elements=self.MAX_ELEMENTS, error_rate=self.ERROR_RATE)

    def __init__(self):
        self.bf = self.new_bf()

    def add(self, v):
        if self.size <= 0:
            logging.warning("bloom filter reset")
            self.bf = self.new_bf()
        self.bf.add(v)
        self.size -= 1

    def __contains__(self, key):
        return key in self.bf
