# aioshadowsocks
用 asyncio 重写 shadowsocks ~

## 为什么要重写shadowsocks

最近对异步IO非常感兴趣

想通过这个项目的推进来深入了解 `asyncio`

我的另外一个项目 `django-sspanel` 依赖 `ssr`

但该项目已经停止开发了，并且代码写的稍显晦涩

虽然我也尝试过二开，最终还是放弃了

最后考虑了一番，还是决定重新造个轮子

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