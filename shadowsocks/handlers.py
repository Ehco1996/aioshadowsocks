import time
import logging
import asyncio

from shadowsocks.cryptor import Cryptor
from shadowsocks.server_pool import pool
from shadowsocks.utils import parse_header
from shadowsocks import protocol_flag as flag


class TimeoutHandler:
    def __init__(self):
        self._transport = None
        self._last_active_time = time.time()
        self._timeout_limit = 20

    def close(self):
        raise NotImplementedError

    def keep_alive_open(self):
        asyncio.ensure_future(self._keep_alive())

    def keep_alive_active(self):
        self._last_active_time = time.time()

    async def _keep_alive(self):
        while self._transport is not None:
            current_time = time.time()
            if current_time - self._last_active_time > self._timeout_limit:
                self.close()
                break
            else:
                await asyncio.sleep(1)


class LocalHandler(TimeoutHandler):
    '''
    事件循环一共处理五个状态

    STAGE_INIT  初始状态 socket5握手
    STAGE_CONNECT 连接建立阶段 从本地获取addr 进行dns解析
    STAGE_STREAM 建立管道(pipe) 进行socket5传输
    STAGE_DESTROY 结束连接状态
    STAGE_ERROR 异常状态
    '''

    STAGE_INIT = 0
    STAGE_CONNECT = 1
    STAGE_STREAM = 2
    STAGE_DESTROY = -1
    STAGE_ERROR = 255

    def __init__(self, method, password, user):
        TimeoutHandler.__init__(self)

        self.user = user
        self._key = password
        self._method = method

        self._remote = None
        self._cryptor = None
        self._peername = None
        self._transport = None
        self._transport_protocol = None
        self._stage = self.STAGE_DESTROY

    def destroy(self):
        '''尝试优化一些内存泄露的问题'''
        self._stage = self.STAGE_DESTROY
        self._key = None
        self._method = None
        self._cryptor = None
        self._peername = None

    def traffic_filter(self):
        if pool.filter_user(self.user) is False:
            return False
        elif self._transport is None:
            return False
        elif self._transport._sock is None:
            # cpython selector_events _SelectorTransport
            return False
        return True

    def close(self, clean=False):
        if self._transport_protocol == flag.TRANSPORT_TCP:
            if self._transport:
                self._transport.close()
            if self.user and self.user.tcp_count > 0:
                self.user.tcp_count -= 1
        elif self._transport_protocol == flag.TRANSPORT_UDP:
            pass
        else:
            raise NotImplementedError

        if clean:
            self.destroy()

    def write(self, data):
        '''
        针对tcp/udp分别写数据
        '''
        # filter traffic
        if self.traffic_filter() is False:
            self.close(clean=True)
            return
        if self._transport_protocol == flag.TRANSPORT_TCP:
            try:
                self._transport.write(data)
                # 记录下载流量
                self.user.once_used_d += len(data)
            except MemoryError:
                logging.warning(
                    'memory boom user_id: {}'.format(self.user.user_id))
                pool.add_user_to_jail(self.user.user_id)
                self.close(clean=True)
        elif self._transport_protocol == flag.TRANSPORT_UDP:
            self._transport.sendto(data, self._peername)
        else:
            raise NotImplementedError

    def handle_tcp_connection_made(self, transport):
        '''
        处理tcp连接

        get_extra_info asyncio Transports api
        doc: https://docs.python.org/3/library/asyncio-protocol.html
        '''
        self._stage = self.STAGE_INIT
        self._transport_protocol = flag.TRANSPORT_TCP
        # filter tcp connction
        if not pool.filter_user(self.user):
            transport.close()
            self.close(clean=True)
            return
        self._transport = transport
        # get the remote address to which the socket is connected
        self._peername = self._transport.get_extra_info('peername')
        self.keep_alive_open()

        try:
            self._cryptor = Cryptor(
                self._method, self._key, self._transport_protocol)
            logging.debug('tcp connection made')
        except NotImplementedError:
            logging.warning('not support cipher')
            transport.close()
            self.close(clean=True)

    def handle_udp_connection_made(self, transport, peername):
        '''
        处理udp连接
        '''
        self._stage = self.STAGE_INIT
        self._transport = transport
        self._transport_protocol = flag.TRANSPORT_UDP
        self._peername = peername

        try:
            self._cryptor = Cryptor(
                self._method, self._key, self._transport_protocol)
            logging.debug('udp connection made')
        except NotImplementedError:
            logging.warning('not support cipher:{}'.format(self._method))
            transport.close()
            self.close(clean=True)

    def handle_data_received(self, data):
        # 累计并检查用户流量
        self.user.once_used_u += len(data)
        try:
            data = self._cryptor.decrypt(data)
        except RuntimeError as e:
            logging.warning('decrypt data error {}'.format(e))
            self.close(clean=True)
            return

        if self._stage == self.STAGE_INIT:
            coro = self._handle_stage_init(data)
            asyncio.ensure_future(coro)
        elif self._stage == self.STAGE_CONNECT:
            coro = self._handle_stage_connect(data)
            asyncio.ensure_future(coro)
        elif self._stage == self.STAGE_STREAM:
            self._handle_stage_stream(data)
        elif self._stage == self.STAGE_ERROR:
            self._handle_stage_error()
        else:
            logging.warning('unknown stage:{}'.format(self._stage))

    def handle_eof_received(self):
        logging.debug('eof received')
        self.close()

    def handle_connection_lost(self, exc):
        logging.debug('lost exc={exc}'.format(exc=exc))
        self.close()

    async def _handle_stage_init(self, data):
        '''
        初始化连接状态(握手后建立链接)

        doc:
        https://docs.python.org/3/library/asyncio-eventloop.html
        '''
        from shadowsocks.tcpreply import RemoteTCP
        from shadowsocks.udpreply import RemoteUDP

        atype, dst_addr, dst_port, header_length = parse_header(data)

        if not dst_addr:
            logging.warning(
                'not valid data atype：{} user: {}'.format(atype, self.user))
            self.close(clean=True)
            return
        else:
            payload = data[header_length:]

        # 获取事件循环
        loop = asyncio.get_event_loop()
        if self._transport_protocol == flag.TRANSPORT_TCP:
            self._stage = self.STAGE_CONNECT

            # 尝试建立tcp连接，成功的话将会返回 (transport,protocol)
            tcp_coro = loop.create_connection(lambda: RemoteTCP(
                dst_addr, dst_port, payload, self._method, self._key, self),
                dst_addr, dst_port)
            try:
                remote_transport, remote_instance = await tcp_coro
                # 记录用户的tcp连接数
                self.user.tcp_count += 1
            except (IOError, OSError) as e:
                logging.debug(
                    'connection faild , {} e: {}'.format(type(e), e))
                self.close()
                self._stage = self.STAGE_DESTROY
            except Exception as e:
                logging.warning(
                    'connection failed, {} e: {}'.format(type(e), e))
                self._stage = self.STAGE_ERROR
                self.close()
            else:
                logging.debug(
                    'connection established,remote {}'.format(remote_instance))
                self._remote = remote_instance
                self._stage = self.STAGE_STREAM
        elif self._transport_protocol == flag.TRANSPORT_UDP:
            self._stage = self.STAGE_INIT
            # 异步建立udp连接，并存入future对象
            udp_coro = loop.create_datagram_endpoint(lambda: RemoteUDP(
                dst_addr, dst_port, payload, self._method, self._key,  self),
                remote_addr=(dst_addr, dst_port))
            asyncio.ensure_future(udp_coro)
        else:
            raise NotImplementedError

    async def _handle_stage_connect(self, data):

        logging.debug('wait until the connection established')
        # 在握手之后，会耗费一定时间来来和remote建立连接
        # 但是ss-client并不会等这个时间 所以我们在这里手动sleep一会
        for i in range(25):
            if self._stage == self.STAGE_CONNECT:
                await asyncio.sleep(0.2)
            elif self._stage == self.STAGE_STREAM:
                logging.debug('connection established')
                self._remote.write(data)
                return
            else:
                logging.debug(
                    'some error happed stage {}'.format(self._stage))
        #  5s之后连接还没建立的话 超时处理
        logging.warning(
            'time out to connect remote stage {}'.format(self._stage))
        self.close(clean=True)

    def _handle_stage_stream(self, data):
        logging.debug('realy data length {}'.format(len(data)))
        self.keep_alive_active()
        self._remote.write(data)

    def _handle_stage_error(self):
        self.close()
