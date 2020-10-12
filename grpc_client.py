import asyncio

from grpclib.client import Channel

from shadowsocks.protos.aioshadowsocks_grpc import ssStub
from shadowsocks.protos.aioshadowsocks_pb2 import (
    FindAccessUserReq,
    HealthCheckReq,
    UserIdReq,
    UserReq,
)


class Client:
    def __init__(self):
        self.channel = Channel("127.0.0.1", 5000)
        self.stub = ssStub(self.channel)

    async def get_user(self, user_id: int):
        user = await self.stub.GetUser(UserIdReq(user_id=1))
        print(f"user: {user}")

    async def list_user(self, tcp_conn_num):
        res = await self.stub.ListUser(UserReq(tcp_conn_num=tcp_conn_num))
        print(f"list_user: {res}")

    async def healcheck(self, url: str):
        res = await self.stub.HealthCheck(HealthCheckReq(url=url))
        print(f"health: {res}")

    async def find_access_user(self):
        res = await self.stub.FindAccessUser(
            FindAccessUserReq(method="chacha20-ietf-poly1305")
        )
        print(f"health: {res}")

    def close(self):
        self.channel.close()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    client = Client()
    # url = "https://www.zhihu.com/"

    # job  = loop.create_task(client.healcheck(url))
    job = loop.create_task(client.find_access_user())
    # job = loop.create_task(client.list_user(0))
    loop.run_until_complete(job)
    client.close()
