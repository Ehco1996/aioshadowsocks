import time
import socket
import struct
import logging
import asyncio

from shadowsocks.cryptor import Cryptor
from shadowsocks import protocol_flag as flag


class BaseTimeoutHandler:
    def __init__(self):
        self._transport = None
        self._last_active_time = time.time()
        self._timeout_limit = 20

    def close(self):
        '''由子类实现'''
        raise NotImplementedError

    def check_alive(self):
        '''
        判断是否timeout
        每次建立连接时都应该调用本方法
        '''
        asyncio.ensure_future(self._check_alive())

    def keep_alive_active(self):
        '''
        记录心跳时间
        每次传输数据时都应该调用本方法
        '''
        self._last_active_time = time.time()

    async def _check_alive(self):
        while self._transport is not None:
            current_time = time.time()
            if current_time - self._last_active_time > self._timeout_limit:
                self.close()
                break
            else:
                await asyncio.sleep(1)


class LocalHandler(BaseTimeoutHandler):
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

    def __init__(self, method, password):
        BaseTimeoutHandler.__init__(self)
        self._key = password
        self._method = method

        self._logger = None
        self._remote = None
        self._cryptor = None
        self._peername = None
        self._transport = None
        self._transport_protocol = None
        self._stage = self.STAGE_DESTROY

    def close(self):
        '''
        针对tcp/udp分别关闭连接
        '''
        if self._transport_protocol == flag.TRANSPORT_TCP:
            if self._transport is not None:
                self._transport.close()
        elif self._transport_protocol == flag.TRANSPORT_UDP:
            # TODO 断开udp连接
            pass
        else:
            raise NotImplementedError

    def write(self, data):
        '''
        针对tcp/udp分别写数据
        '''
        if self._transport_protocol == flag.TRANSPORT_TCP:
            self._transport.write(data)
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
        self.check_alive()

        self._stage = self.STAGE_INIT
        self._transport = transport
        self._transport_protocol = flag.TRANSPORT_TCP
        self._cryptor = Cryptor(self._method, self._key)
        # get the remote address to which the socket is connected
        self._peername = self._transport.get_extra_info('peername')

        self._logger = logging.getLogger(
            '<LocalTCP{0} {1}>'.format(self._peername, hex(id(self))))
        self._logger.debug('tcp connection made')

    def handle_udp_connection_made(self, transport, peername):
        '''
        处理udp连接
        '''
        self.check_alive()

        self._stage = self.STAGE_INIT
        self._transport = transport
        self._transport_protocol = flag.TRANSPORT_UDP
        self._cryptor = Cryptor(self._method, self._key)
        self._peername = peername

        self._logger = logging.getLogger(
            '<LocalUDP{0} {1}>'.format(self._peername, hex(id(self))))
        self._logger.debug('udp connection made')

    def handle_data_received(self, data):
        self._logger.debug('received data length: {}'.format(len(data)))
        data = self._cryptor.decrypt(data)
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
            self._logger.warning('unknown stage:{}'.format(self._stage))

    def handle_eof_received(self):
        self._logger.debug('eof received')

    def handle_connection_lost(self, exc):
        self._logger.debug('lost exc={exc}'.format(exc=exc))
        if self._remote is not None:
            self._remote.close()

    async def _handle_stage_init(self, data):
        '''
        初始化连接状态(握手后建立链接)

        doc:
        https://docs.python.org/3/library/asyncio-eventloop.html
        '''
        from shadowsocks.tcpreply import RemoteTCP  # noqa
        from shadowsocks.udpreply import RemoteUDP  # noqa

        atype = data[0]
        if atype == flag.ATYPE_IPV4:
            dst_addr = socket.inet_ntop(socket.AF_INET, data[1:5])
            dst_port = struct.unpack('!H', data[5:7])[0]
            payload = data[7:]
        elif atype == flag.ATYPE_IPV6:
            dst_addr = socket.inet_ntop(socket.AF_INET6, data[1:17])
            dst_port = struct.unpack('!H', data[17:19])[0]
            payload = data[19:]
        elif atype == flag.ATYPE_DOMAINNAME:
            domain_length = data[1]
            domain_index = 2 + domain_length
            dst_addr = data[2:domain_index]
            dst_port = struct.unpack(
                '!H', data[domain_index:domain_index + 2])[0]
            payload = data[domain_index + 2:]
        else:
            self._logger.warning('unknown atype: {}'.format(atype))
            self.close()
            return

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
            except (IOError, OSError) as e:
                self._logger.debug(
                    'connection faild , {} e: {}'.format(type(e), e))
                self.close()
                self._stage = self.STAGE_DESTROY
            except Exception as e:
                self._logger.warning(
                    'connection failed, {} e: {}'.format(type(e), e))
                self.close()
                self._stage = self.STAGE_ERROR
            else:
                self._logger.debug(
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

        self._logger.debug('wait until the connection established')
        # 在握手之后，会耗费一定时间来来和remote建立连接
        # 但是ss-client并不会等这个时间 所以我们在这里手动sleep一会
        for i in range(25):
            if self._stage == self.STAGE_CONNECT:
                await asyncio.sleep(0.2)
            elif self._stage == self.STAGE_STREAM:
                self._logger.debug('connection established')
                self._remote.write(data)
                return
            else:
                self._logger.debug(
                    'some error happed stage {}'.format(self._stage))
        #  5s之后连接还没建立的话 超时处理
        self._logger.waring(
            'time out to connect remote stage {}'.format(self._stage))
        return

    def _handle_stage_stream(self, data):
        self._logger.debug('realy data length {}'.format(len(data)))
        self.keep_alive_active()
        self._remote.write(data)

    def _handle_stage_error(self):
        self.close()
