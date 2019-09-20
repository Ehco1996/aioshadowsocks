from shadowsocks.mdb import models as m
from shadowsocks.protos import aioshadowsocks_pb2
from shadowsocks.protos import aioshadowsocks_grpc


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
        await stream.send_message(aioshadowsocks_pb2.User(**user.to_dict()))

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
        await stream.send_message(aioshadowsocks_pb2.User(**user.to_dict()))

    async def GetUser(self, stream):
        request = await stream.recv_message()
        user = m.User.get_by_id(request.user_id)
        await stream.send_message(aioshadowsocks_pb2.User(**user.to_dict()))

    async def DeleteUser(self, stream):
        request = await stream.recv_message()
        user = m.User.get_by_id(request.user_id)
        user.server.close_server()
        user.delete_instance()
        await stream.send_message(aioshadowsocks_pb2.Empty())

    async def InitUserServer(self, stream):
        request = await stream.recv_message()
        user = m.User.get_by_id(request.user_id)
        user_server, _ = m.UserServer.get_or_create(user_id=request.user_id)
        await user_server.init_server(user)
        await stream.send_message(
            aioshadowsocks_pb2.UserServer(
                **user_server.to_dict(extra_attrs=["is_running"])
            )
        )

    async def GetUserServer(self, stream):
        # TODO  修改proto 增加字段
        request = await stream.recv_message()
        user_server = m.UserServer.get_by_id(request.user_id)
        await stream.send_message(
            aioshadowsocks_pb2.UserServer(
                **user_server.to_dict(extra_attrs=["is_running"])
            )
        )

    async def StopUserServer(self, stream):
        request = await stream.recv_message()
        user_server = m.UserServer.get_by_id(request.user_id)
        user_server.close_server()
        await stream.send_message(aioshadowsocks_pb2.Empty())
