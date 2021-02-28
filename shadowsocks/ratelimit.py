from time import time


class TrafficRateLimit:
    KB = 1024
    MEGABIT = KB * 125

    def __init__(self, capacity, rate):
        """
        令牌桶法按照带宽限速限速
        capacity: 带宽
        rate: 速率 capacity/second
        """
        self.capacity = float(capacity)
        self.rate = rate

        self._remain_traffic = self.capacity
        self._last_time = time()

    def consume(self, traffic_lens):
        self.fill()
        # NOTE _remain_traffic 可以为负数
        self._remain_traffic -= traffic_lens

    def fill(self):
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
        self.fill()
        return self._remain_traffic < 0
