import time
import asyncio

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

    def __init__(self, password):
        BaseTimeoutHandler.__init__()
        self._key = password

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
