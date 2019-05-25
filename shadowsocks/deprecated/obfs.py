import datetime
from urllib import parse


class BaseHeader:
    @property
    def token(self):
        raise NotImplementedError


class HttpHeader(BaseHeader):
    def __init__(self, content):
        self.content = content.decode()
        temp = self.content.split()
        self.method = temp[0]
        self.path = temp[1]

        self._query_dict = None
        self._header_dict = None

    def _parse_header(self):
        header_content = self.content.split("\r\n\r\n", 1)[0].split("\r\n")[1:]
        result = {}
        for line in header_content:
            k, v = line.split(": ")
            result[k] = v
        return result

    def _parse_query(self):
        qs = parse.urlsplit(self.path).query
        return {k: v[0] for k, v in parse.parse_qs(qs).items()}

    @property
    def header_dict(self):
        if not self._header_dict:
            self._header_dict = self._parse_header()
        return self._header_dict

    @property
    def query_dict(self):
        if not self._query_dict:
            self._query_dict = self._parse_query()
        return self._query_dict

    @property
    def host(self):
        return self.header_dict.get("Host", "")

    @property
    def token(self):
        return self.query_dict.get("token", "")


class HttpSimpleObfs:

    HTTP_HEAD_END_FLAG = b"\r\n\r\n"

    def __init__(self, method="http_simple"):
        self.method = method
        self.has_sent_header = False
        self.has_recv_header = False
        self.header = None

    def __repr__(self):
        return f"<OBFS:{self.method}>"

    def server_encode(self, buf):
        if self.has_sent_header:
            return buf
        header = b"HTTP/1.1 200 OK\r\nConnection: keep-alive\r\n"
        header += b"Content-Encoding: gzip\r\nContent-Type: text/html\r\nDate: "
        header += datetime.datetime.now().strftime("%a, %d %b %Y %H:%M:%S GMT").encode()
        header += b"\r\nServer: nginx\r\nVary: Accept-Encoding"
        header += self.HTTP_HEAD_END_FLAG
        self.has_sent_header = True
        return header + buf

    def _split_header_from_buf(self, buf):
        """return ret_buf,header_buf"""
        head_index = buf.find(self.HTTP_HEAD_END_FLAG) + len(self.HTTP_HEAD_END_FLAG)
        return buf[head_index:], buf[:head_index]

    def server_decode(self, buf):
        """return：ret_buf,header"""
        if self.has_recv_header:
            return buf, self.header

        if self.HTTP_HEAD_END_FLAG in buf:
            ret_buf, header_buf = self._split_header_from_buf(buf)
            self.has_recv_header = True
            self.header = HttpHeader(header_buf)
            return ret_buf, self.header
        else:
            return buf, self.header


class Obfs:

    OBFS_CLS_MAP = {"http_simple": HttpSimpleObfs}

    def __new__(cls, method):
        obfs_cls = cls.OBFS_CLS_MAP.get(method)
        if obfs_cls:
            return obfs_cls(method)

    @property
    def token(self):
        return self.header.token
