import datetime


class ObfsHeader:
    def __init__(self, host):
        self.host = host


class HttpSimpleObfs:

    HTTP_HEAD_END_FLAG = b"\r\n\r\n"

    def __init__(self, method="http_simple"):
        self.method = method
        self.has_sent_header = False
        self.has_recv_header = False
        self.header = None

    def __repr__(self):
        return self.method

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

    def _get_host_from_http_header(self, header_buf):
        host = None
        for line in header_buf.split(b"\r\n"):
            line = line.decode()
            host_index = line.find("Host:")
            if host_index != -1:
                host = line[host_index + 5 :].strip()
            if host:
                break
        return host

    def _parse_http_header(self, header_buf):
        host = self._get_host_from_http_header(header_buf)
        header = ObfsHeader(host)
        return header

    def server_decode(self, buf):
        """return：ret_buf,header"""
        if self.has_recv_header:
            return buf, self.header

        if self.HTTP_HEAD_END_FLAG in buf:

            ret_buf, header_buf = self._split_header_from_buf(buf)
            self.has_recv_header = True
            self.header = self._parse_http_header(header_buf)
            return ret_buf, self.header
        else:
            return buf, self.header


class Obfs:

    OBFS_CLS_MAP = {"http_simple": HttpSimpleObfs}

    def __new__(cls, method):
        obfs_cls = cls.OBFS_CLS_MAP.get(method)
        if obfs_cls:
            return obfs_cls(method)

    def __getattr__(self, name):
        return getattr(self._backend, name)
