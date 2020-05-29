import uuid

from shadowsocks.utils import AutoResetBloomFilter


def test_benchmark_bf(benchmark):
    abf = AutoResetBloomFilter()

    def ben_add():
        abf.add(uuid.uuid4().hex)

    benchmark(ben_add)
