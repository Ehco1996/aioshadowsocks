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

    def consume(self, traffic_lens):
        if self.capacity == float(0):
            return False

        time_delta = time() - self._last_time
        if time_delta > 1:
            self._remain_traffic = self.capacity
        else:
            increment = time_delta * self.rate
            self._remain_traffic = min(increment + self._remain_traffic, self.capacity)

        if traffic_lens > self._remain_traffic:
            return True
        else:
            self._remain_traffic -= traffic_lens
            self._last_time = time()

    @property
    def human_rate(self):
        return f"now rate is: {round(self.rate / self.MEGABIT, 1)} Mbps"
