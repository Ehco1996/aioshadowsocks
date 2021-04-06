import grpc

from shadowsocks.gen.sync_protos.aioshadowsocks_pb2 import (
    DecryptDataReq,
    FindAccessUserReq,
    User,
    UserIdReq,
)
from shadowsocks.gen.sync_protos.aioshadowsocks_pb2_grpc import ssStub


class SSClient:
    def __init__(self, rpc_endpint="127.0.0.1:5000") -> None:
        self.channel = grpc.insecure_channel(rpc_endpint)
        self.stub = ssStub(self.channel)

    def get_user(self, user_id: int) -> User:
        return self.stub.GetUser(UserIdReq(user_id=user_id))

    def find_access_user(self, port, method, ts_protocol, data):
        req = FindAccessUserReq(
            port=port, method=method, ts_protocol=ts_protocol, data=data
        )
        return self.stub.FindAccessUser(req)

    def decrypt_data(self, uuid, user_id, method, password, data):
        req = DecryptDataReq(
            uuid=uuid, user_id=user_id, method=method, password=password, data=data
        )
        return self.stub.DecryptData(req).data
