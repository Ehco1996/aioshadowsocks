# aioshadowsocks
用 asyncio 重写 shadowsocks ~


### 当前进度~

- [x] TCP
- [x] UDP
- [x] Basic Cipher (aes)
- [x] WebTransfer
- [ ] ManyUser One Port
- [ ] More Cipher (ahead)

## 为什么要重写shadowsocks

最近对异步IO非常感兴趣

想通过这个项目的推进来深入了解 `asyncio`

我的另外一个项目 `django-sspanel` 依赖 `ssr`

但该项目已经停止开发了，并且代码写的稍显晦涩

虽然我也尝试过二开，最终还是放弃了

最后考虑了一番，还是决定重新造个轮子



## shadowsocks原理

ss基于`socket5协议`
其最基本的工作流可以抽象成三个阶段: 1 握手 2 建立连接 3 传输数据

具体来说：

* client 向 proxy 发出建立连接的请求
* proxy 做出回应 表示自己收到请求
* client 确认后再次向proxy发送 目标server(真正想要访问的地址)的 ip 和 port
* proxy 尝试和 目标server 建立连接，并向client 返回自身的 ip 和 port
* client 与 proxy 建立 tcp/udp 连接
* proxy 将 client 发送的信息传给目标server 并返回server的response给client

> 关于原理网上有一张非常简单图

![](http://opj9lh0x4.bkt.clouddn.com/18-7-28/71187557.jpg)

这里ss能够突破gfw的封锁的关键是将传输的数据进行了加密

client首先以soket5协议与 sslocal 建立连接

sslocal将数据流进行加密并后再和 ss server 进行通讯

这样经过数据流过gfw的时候，就是很普通的tcp包，由于没有解密的key，gfw也就不能解密 

最后ss server将加密后的数据解密 经过处理之后，再次向client发送加密数据


## 使用教程

* 安装依赖

```sh
wget https://bootstrap.pypa.io/get-pip.py

python3 get-pip.py

pip3 install -r requirements.txt
```

* 使用

```python
python server.py
```
