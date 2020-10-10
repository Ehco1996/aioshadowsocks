import asyncio
import inspect
import logging
import os
import signal

import sentry_sdk
import uvloop
from aiohttp import web
from grpclib.events import RecvRequest, listen
from grpclib.server import Server
from prometheus_async import aio
from sentry_sdk.integrations.aiohttp import AioHttpIntegration

from shadowsocks.mdb import BaseModel, models
from shadowsocks.proxyman import ProxyMan
from shadowsocks.services import AioShadowsocksServicer


async def logging_grpc_request(event: RecvRequest) -> None:
    logging.info(f"{event.method_name} called!")


class App:
    def _init_config(self):
        self.config = {
            "LISTEN_HOST": os.getenv("SS_LISTEN_HOST", "0.0.0.0"),
            "GRPC_HOST": os.getenv("SS_GRPC_HOST", "127.0.0.1"),
            "GRPC_PORT": os.getenv("SS_GRPC_PORT", "5000"),
            "SENTRY_DSN": os.getenv("SS_SENTRY_DSN"),
            "API_ENDPOINT": os.getenv("SS_API_ENDPOINT"),
            "LOG_LEVEL": os.getenv("SS_LOG_LEVEL", "info"),
            "SYNC_TIME": int(os.getenv("SS_SYNC_TIME", 60)),
            "STREAM_DNS_SERVER": os.getenv("SS_STREAM_DNS_SERVER"),
            "METRICS_PORT": os.getenv("SS_METRICS_PORT"),
            "TIME_OUT_LIMIT": int(os.getenv("SS_TIME_OUT_LIMIT", 60)),
            "USER_TCP_CONN_LIMIT": int(os.getenv("SS_TCP_CONN_LIMIT", 60)),
        }

        self.grpc_host = self.config["GRPC_HOST"]
        self.grpc_port = self.config["GRPC_PORT"]
        self.log_level = self.config["LOG_LEVEL"]
        self.sync_time = self.config["SYNC_TIME"]
        self.sentry_dsn = self.config["SENTRY_DSN"]
        self.listen_host = self.config["LISTEN_HOST"]
        self.api_endpoint = self.config["API_ENDPOINT"]
        self.timeout_limit = self.config["TIME_OUT_LIMIT"]
        self.stream_dns_server = self.config["STREAM_DNS_SERVER"]
        self.user_tcp_conn_limit = self.config["USER_TCP_CONN_LIMIT"]
        self.metrics_port = self.config["METRICS_PORT"]

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
        level = log_levels.get(self.log_level.upper(), 10)
        logging.basicConfig(
            format="[%(levelname)s]%(asctime)s - %(filename)s - %(funcName)s "
            "line:%(lineno)d: - %(message)s",
            level=level,
        )

    def _init_memory_db(self):

        for _, model in inspect.getmembers(models, inspect.isclass):
            if issubclass(model, BaseModel) and model != BaseModel:
                model.create_table()
                logging.info(f"正在创建{model}内存数据库")

    def _init_sentry(self):
        if not self.use_sentry:
            return
        sentry_sdk.init(dsn=self.sentry_dsn, integrations=[AioHttpIntegration()])
        logging.info("Init Sentry Client...")

    def _prepare(self):
        uvloop.install()
        self.loop = asyncio.get_event_loop()
        self._init_config()
        self._init_logger()
        self._init_memory_db()
        self._init_sentry()
        self.loop.add_signal_handler(signal.SIGTERM, self.shutdown)
        self.proxyman = ProxyMan(self.listen_host)

    async def start_grpc_server(self):

        self.grpc_server = Server([AioShadowsocksServicer()], loop=self.loop)
        listen(self.grpc_server, RecvRequest, logging_grpc_request)
        await self.grpc_server.start(self.grpc_host, self.grpc_port)
        logging.info(f"Start grpc Server on {self.grpc_host}:{self.grpc_port}")

    async def start_metrics_server(self):
        app = web.Application()
        app.router.add_get("/metrics", aio.web.server_stats)
        runner = web.AppRunner(app)
        await runner.setup()
        self.metrics_server = web.TCPSite(runner, "0.0.0.0", self.metrics_port)
        await self.metrics_server.start()
        logging.info(
            f"Start Metrics Server At: http://0.0.0.0:{self.metrics_port}/metrics"
        )

    def run_ss_server(self):
        """启动ss server"""
        self._prepare()

        if self.use_json:
            self.loop.create_task(self.proxyman.start_ss_json_server())
        else:
            self.loop.create_task(
                self.proxyman.start_remote_sync_server(
                    self.api_endpoint, self.sync_time
                )
            )

        if self.use_grpc:
            self.loop.create_task(self.start_grpc_server())

        if self.metrics_port:
            self.loop.create_task(self.start_metrics_server())

        try:
            self.loop.run_forever()
        except KeyboardInterrupt:
            self.shutdown()

    def shutdown(self):
        logging.info("正在关闭所有ss server")
        self.proxyman.close_server()
        if self.use_grpc:
            self.grpc_server.close()
            logging.info(f"grpc server closed!")
        if self.metrics_port:
            self.loop.create_task(self.metrics_server.stop())
            logging.info(f"metrics server closed!")
        self.loop.stop()
