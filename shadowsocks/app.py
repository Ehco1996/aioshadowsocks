import asyncio
import inspect
import logging
import os
import signal

import raven
import uvloop
from aiohttp import web
from grpclib.server import Server
from prometheus_async import aio
from raven_aiohttp import AioHttpTransport

# TODO Don't use Model here


class App:
    def __init__(self, debug=False):
        self.debug = debug
        if not self.debug:
            uvloop.install()

        self.loop = asyncio.get_event_loop()
        self.prepared = False

    def _init_config(self):
        self.config = {
            "GRPC_HOST": os.getenv("SS_GRPC_HOST"),
            "GRPC_PORT": os.getenv("SS_GRPC_PORT"),
            "SENTRY_DSN": os.getenv("SS_SENTRY_DSN"),
            "API_ENDPOINT": os.getenv("SS_API_ENDPOINT"),
            "LOG_LEVEL": os.getenv("SS_LOG_LEVEL", "info"),
            "SYNC_TIME": int(os.getenv("SS_SYNC_TIME", 60)),
            "STREAM_DNS_SERVER": os.getenv("SS_STREAM_DNS_SERVER"),
            "ENABLE_METRICS": bool(os.getenv("SS_ENABLE_METRICS", True)),
            "TIME_OUT_LIMIT": int(os.getenv("SS_TIME_OUT_LIMIT", 60)),
            "USER_TCP_CONN_LIMIT": int(os.getenv("SS_TCP_CONN_LIMIT", 60)),
        }

        self.grpc_host = self.config["GRPC_HOST"]
        self.grpc_port = self.config["GRPC_PORT"]
        self.log_level = self.config["LOG_LEVEL"]
        self.sync_time = self.config["SYNC_TIME"]
        self.sentry_dsn = self.config["SENTRY_DSN"]
        self.api_endpoint = self.config["API_ENDPOINT"]
        self.timeout_limit = self.config["TIME_OUT_LIMIT"]
        self.stream_dns_server = self.config["STREAM_DNS_SERVER"]
        self.user_tcp_conn_limit = self.config["USER_TCP_CONN_LIMIT"]

        self.enable_metrics = self.config["ENABLE_METRICS"]
        self.use_sentry = True if self.sentry_dsn else False
        self.use_json = False if self.api_endpoint else True
        self.use_grpc = True if self.grpc_host and self.grpc_port else False

    def _init_logger(self):
        """
        basic log config
        """
        log_levels = {
            "CRITICAL": 50,
            "ERROR": 40,
            "WARNING": 30,
            "INFO": 20,
            "DEBUG": 10,
        }
        if self.debug:
            level = 10
        else:
            level = log_levels.get(self.log_level.upper(), 10)
        logging.basicConfig(
            format="[%(levelname)s]%(asctime)s - %(filename)s - %(funcName)s "
            "line:%(lineno)d: - %(message)s",
            level=level,
        )

    def _init_memory_db(self):
        from shadowsocks.mdb import BaseModel, models

        for _, model in inspect.getmembers(models, inspect.isclass):
            if issubclass(model, BaseModel) and model != BaseModel:
                model.create_table()
                logging.info(f"正在创建{model}内存数据库")

    def _init_sentry(self):
        def sentry_exception_handler(loop, context):
            try:
                raise context["exception"]
            except TimeoutError:
                logging.error(f"socket timeout msg: {context['message']}")
            except Exception:
                logging.error(f"unhandled error msg: {context['message']}")
                self.sentry_client.captureException(**context)

        if not self.use_sentry:
            return
        self.sentry_client = raven.Client(self.sentry_dsn, transport=AioHttpTransport)
        self.loop.set_exception_handler(sentry_exception_handler)
        logging.info("Init Sentry Client...")

    def _prepare(self):
        if self.prepared:
            return
        self._init_config()
        self._init_logger()
        self._init_memory_db()
        self._init_sentry()
        self.loop.add_signal_handler(signal.SIGTERM, self.shutdown)
        self.prepared = True

    async def start_grpc_server(self):
        from shadowsocks.services import AioShadowsocksServicer

        self.grpc_server = Server([AioShadowsocksServicer()], loop=self.loop)
        await self.grpc_server.start(self.grpc_host, self.grpc_port)
        logging.info(f"Start Grpc Server on {self.grpc_host}:{self.grpc_port}")

    async def start_metrics_server(self):
        app = web.Application()
        app.router.add_get("/metrics", aio.web.server_stats)
        runner = web.AppRunner(app)
        await runner.setup()
        self.metrics_server = web.TCPSite(runner, "0.0.0.0", 9888)
        await self.metrics_server.start()
        logging.info(f"Start Metrics Server At: http://0.0.0.0:9888/metrics ")

    def start_json_server(self):
        from shadowsocks.mdb import models

        models.User.create_or_update_from_json("userconfigs.json")
        models.User.init_user_servers()

    def start_remote_sync_server(self):
        from shadowsocks.mdb import models

        try:
            models.User.create_or_update_from_remote(self.api_endpoint)
            models.UserServer.flush_metrics_to_remote(self.api_endpoint)
            models.User.init_user_servers()
        except Exception as e:
            logging.warning(f"sync user error {e}")
        self.loop.call_later(self.sync_time, self.start_remote_sync_server)

    def run(self):
        self._prepare()

        if self.use_json:
            self.start_json_server()
        else:
            self.start_remote_sync_server()

        if self.use_grpc:
            self.loop.create_task(self.start_grpc_server())

        if self.enable_metrics:
            self.loop.create_task(self.start_metrics_server())

        try:
            self.loop.run_forever()
        except KeyboardInterrupt:
            logging.info("正在关闭所有ss server")
            self.shutdown()

    def shutdown(self):
        from shadowsocks.mdb import models

        models.UserServer.shutdown()
        if self.use_grpc:
            self.grpc_server.close()
            logging.info(f"grpc server closed!")
        if self.enable_metrics:
            self.metrics_server.stop()
            logging.info(f"metrics on closed!")

        self.loop.stop()
