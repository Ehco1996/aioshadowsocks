import pytest

from shadowsocks.app import App
from shadowsocks.mdb.models import User


@pytest.fixture
def app():
    app = App()
    app._prepare()
    User.sync_from_json_cron(10)
    return app


def test_find_access_user(app):
    users = User.select(User.port == 1025, User.method == "chacha20-ietf-poly1305")
    first_user = users.first()
    print(first_user)
