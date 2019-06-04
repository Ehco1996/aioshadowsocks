# aioshadowsocks
用 asyncio 重写 shadowsocks

## 为什么要重写shadowsocks

主要想通过这个项目的推进来深入了解 `asyncio`

另外我的一个项目: [django-sspanel](https://github.com/Ehco1996/django-sspanel) 依赖`shadowsocksr`

但该项目已经停止开发了，所以决定重新造个轮子

## 主要功能

* tcp/udp 代理
* 开放了grpc接口(类似ss-manager)


## rpc proto

```proto3
syntax = "proto3";

package aioshadowsocks;

// REQ
message UserIdReq { int32 user_id = 1; }

message UserReq {
  int32 user_id = 1;
  int32 port = 2;
  string method = 3;
  string password = 4;
  bool enable = 5;
}

// OBJ
message Empty {}

message User {
  int32 user_id = 1;
  int32 port = 2;
  string method = 3;
  string password = 4;
  bool enable = 5;
}

message UserServer {
  int32 user_id = 1;
  int64 upload_traffic = 2;
  int64 download_traffic = 3;
  repeated string ip_list = 4;
  bool is_running = 5;
}
// service
service ss {
  rpc CreateUser(UserReq) returns (User) {}
  rpc UpdateUser(UserReq) returns (User) {}
  rpc GetUser(UserIdReq) returns (User) {}
  rpc DeleteUser(UserIdReq) returns (Empty) {}
  rpc InitUserServer(UserIdReq) returns (UserServer) {}
  rpc GetUserServer(UserIdReq) returns (UserServer) {}
  rpc StopUserServer(UserIdReq) returns (Empty) {}
}
```




## 使用

* 安装依赖

```sh
wget https://bootstrap.pypa.io/get-pip.py

python3 get-pip.py

pip3 install -r requirements.txt
```

* 注入环境变量

`export SS_API_ENDPOINT="https://xxx/com"`

* 使用

```python
python server.py
```

## Docker Version

1. install docker

```sh
curl -sSL https://get.docker.com/ | sh
```

2. install docker-compose

```sh
sudo curl -L "https://github.com/docker/compose/releases/download/1.23.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
```

3. apply executable permissions

```sh
sudo chmod +x /usr/local/bin/docker-compose
```

4. run server

```sh
docker-compose up
```