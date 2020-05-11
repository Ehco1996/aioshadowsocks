import asyncio

from grpclib.client import Channel


from shadowsocks.protos.aioshadowsocks_pb2 import (
    UserIdReq,
    User,
    HealthCheckReq,
    HealthCheckRes,
)
from shadowsocks.protos.aioshadowsocks_grpc import ssStub


class Client:
    def __init__(self, loop):
        self.channel = Channel("127.0.0.1", 5000, loop=loop)
        self.stub = ssStub(self.channel)

    async def get_user(self, user_id: int):
        user = await self.stub.GetUser(UserIdReq(user_id=1))
        print(f"user: {user}")

    async def healcheck(self, url: str):
        res = await self.stub.HealthCheck(HealthCheckReq(url=url))
        print(f"health: {res}")

    def close(self):
        self.channel.close()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    client = Client(loop)
    url = "https://www.zhihu.com/"

    # health_job  = loop.create_task(client.healcheck(url))
    get_user_job = loop.create_task(client.get_user(1))

    loop.run_until_complete(get_user_job)
    client.close()
