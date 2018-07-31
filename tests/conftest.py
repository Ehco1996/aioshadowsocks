import pytest


@pytest.fixture
def crypto_data():
    test_data = ['123', 'python', 'python2 or python3', '万里城墙']
    return [o.encode() for o in test_data]


@pytest.fixture
def support_methods():
    methods = ['aes-128-cfb', 'aes-192-cfb', 'aes-256-cfb']
    return methods
