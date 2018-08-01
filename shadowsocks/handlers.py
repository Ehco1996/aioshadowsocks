import time
import socket
import struct
import logging
import asyncio


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
