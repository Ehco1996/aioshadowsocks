import pytest


@pytest.fixture
def crypto_data():
    test_data = ['123', 'python', 'python2 or python3', '万里城墙']
    return [o.encode() for o in test_data]
