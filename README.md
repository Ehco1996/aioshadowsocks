# aioshadowsocks

用 asyncio 重写 shadowsocks

![Publish Docker](https://github.com/Ehco1996/aioshadowsocks/workflows/Publish%20Docker/badge.svg?branch=master)

## 为什么要重写shadowsocks

主要想通过这个项目的推进来深入了解 `asyncio` 

另外我的一个项目: [django-sspanel](https://github.com/Ehco1996/django-sspanel) 依赖 `shadowsocksr` 

但该项目已经停止开发了，所以决定重新造个轮子

## 主要功能

* tcp/udp 代理
* 流量统计
* 速率控制
* 开放了grpc接口(类似ss-manager)

## rpc proto

``` protobuf
syntax = "proto3";

package aioshadowsocks;

// REQ
message UserIdReq { int32 user_id = 1; }
message PortReq { int32 port = 1; }

message UserReq {
  int32 user_id = 1;
  int32 port = 2;
  string method = 3;
  string password = 4;
  bool enable = 5;
}

// RES
message Empty {}

message User {
  int32 user_id = 1;
  int32 port = 2;
  string method = 3;
  string password = 4;
  bool enable = 5;
  int32 speed_limit = 6;
  int32 access_order = 7;
  bool need_sync = 8;
  repeated string ip_list = 9;
  int32 tcp_conn_num = 10;
  int64 upload_traffic = 11;
  int64 download_traffic = 12;
}

// service
service ss {
  rpc CreateUser(UserReq) returns (User) {}
  rpc UpdateUser(UserReq) returns (User) {}
  rpc GetUser(UserIdReq) returns (User) {}
  rpc DeleteUser(UserIdReq) returns (Empty) {}
}
```

## 编译protos

`pip3 install grpcio-tools` 

`python3 -m grpc_tools.protoc -I. --python_out=. --python_grpc_out=. shadowsocks/protos/aioshadowsocks.proto` 

## 使用

* 安装依赖

``` sh
wget https://bootstrap.pypa.io/get-pip.py

python3 get-pip.py

pip3 install -r requirements.txt
```

* 注入环境变量

`export SS_API_ENDPOINT="https://xxx/com"` 

* 使用

``` python
python server.py
```

## Docker Version

1. install docker

``` sh
curl -sSL https://get.docker.com/ | sh
```

2. install docker-compose

``` sh
sudo curl -L "https://github.com/docker/compose/releases/download/1.23.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
```

3. apply executable permissions

``` sh
sudo chmod +x /usr/local/bin/docker-compose
```

4. run server

``` sh
docker-compose up
```
