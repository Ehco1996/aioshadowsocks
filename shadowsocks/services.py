from shadowsocks.mdb import models as m
from shadowsocks.protos import aioshadowsocks_grpc
from shadowsocks.protos.aioshadowsocks_pb2 import (HealthCheckRes, User,
                                                   UserList)


class AioShadowsocksServicer(aioshadowsocks_grpc.ssBase):
    async def CreateUser(self, stream):
        request = await stream.recv_message()
        data = {
            "user_id": request.user_id,
            "port": request.port,
            "method": request.method,
            "password": request.password,
            "enable": request.enable,
        }
        user = m.User.create_or_update_user_from_data(data)
        await stream.send_message(User(**user.to_dict()))

    async def UpdateUser(self, stream):
        request = await stream.recv_message()
        data = {
            "user_id": request.user_id,
            "port": request.port,
            "method": request.method,
            "password": request.password,
            "enable": request.enable,
        }
        user = m.User.create_or_update_user_from_data(data)
        await stream.send_message(User(**user.to_dict()))

    async def GetUser(self, stream):
        request = await stream.recv_message()
        user = m.User.get_by_id(request.user_id)
        await stream.send_message(User(**user.to_dict()))

    async def DeleteUser(self, stream):
        request = await stream.recv_message()
        user = m.User.get_by_id(request.user_id)
        user.server.close_server()
        user.delete_instance()
        await stream.send_message(aioshadowsocks_pb2.Empty())

    async def ListUser(self, stream):
        request = await stream.recv_message()
        users = m.User.select().where(m.User.tcp_conn_num <= request.tcp_conn_num)
        res = UserList(data=[user.to_dict() for user in users])
        await stream.send_message(res)

    async def HealthCheck(self, stream):
        request = await stream.recv_message()
        url = request.url
        await stream.send_message(HealthCheckRes(status_code="200", duration=100))
