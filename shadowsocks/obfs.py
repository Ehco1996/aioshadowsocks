import datetime


class HttpSimpleObfs:

    HTTP_HEAD_END_FLAG = b"\r\n\r\n"

    def __init__(self, method="http_simple"):
        self.method = method
        self.has_sent_header = False
        self.has_recv_header = False

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

    def _get_data_from_http_header(self, buf):
        return buf[buf.find(self.HTTP_HEAD_END_FLAG) + 4 :]

    def _get_host_from_http_header(self, buf):
        host = None
        http_head = buf[: buf.find(self.HTTP_HEAD_END_FLAG) + 4]
        for line in http_head.split(b"\r\n"):
            line = line.decode()
            host_index = line.find("Host:")
            if host_index != -1:
                host = line[host_index + 5 :].strip()
        return host

    def server_decode(self, buf):
        """return：ret_buf,host"""
        if self.has_recv_header:
            return buf, None

        if self.HTTP_HEAD_END_FLAG in buf:
            ret_buf = self._get_data_from_http_header(buf)
            host = self._get_host_from_http_header(buf)
            self.has_recv_header = True
            return ret_buf, host
        else:
            return buf, None


class AbstractObfs:

    OBFS_CLS_MAP = {"http_simple": HttpSimpleObfs}

    def __new__(cls, method):
        obfs_cls = cls.OBFS_CLS_MAP.get(method)
        if obfs_cls:
            return obfs_cls(method)

    def __getattr__(self, name):
        return getattr(self._backend, name)
