from time import time


class TrafficRateLimit:
    KB = 1024
    MEGABIT = KB * 125

    def __init__(self, capacity, rate=None):
        """
        令牌桶法按照带宽限速限速
        capacity: 带宽
        rate: 速率 capacity/second
        """
        self.capacity = float(capacity)
        if not rate:
            self.rate = self.capacity
        else:
            self.rate = rate

        self._remain_traffic = self.capacity
        self._last_time = time()
        self._cur_rate = 0

    def consume(self, traffic_lens):
        time_delta = time() - self._last_time
        self.fill(time_delta)

        # NOTE _remain_traffic 可以为负数
        self._remain_traffic -= traffic_lens
        if self._remain_traffic > 0:
            self._cur_rate = traffic_lens / time_delta

    def fill(self, time_delta=None):
        if not time_delta:
            time_delta = time() - self._last_time
        self._last_time += time_delta

        if self._remain_traffic < 0:
            # NOTE 给超速的用户补上
            increment = time_delta * self.rate
            self._remain_traffic += increment
            return

        if time_delta > 1:
            self._remain_traffic = self.capacity
        else:
            increment = time_delta * self.rate
            self._remain_traffic = min(increment + self._remain_traffic, self.capacity)

    @property
    def cur_rate(self):
        return f"now rate is: {round(self._cur_rate / self.MEGABIT, 1)} Mbps"

    @property
    def limited(self):
        if self.capacity == float(0):
            return False
        return self._remain_traffic < 0


class TcpConnRateLimit:
    def __init__(self, capacity):
        self.capacity = capacity
        self.tcp_conn_num = 0

    def incr_tcp_conn_num(self, num):
        self.tcp_conn_num += num

    @property
    def limited(self):
        return self.tcp_conn_num > self.capacity

