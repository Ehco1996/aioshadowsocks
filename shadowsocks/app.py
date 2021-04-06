import asyncio
import logging
import os
import signal

import sentry_sdk
from aiohttp import web
from grpclib.events import RecvRequest, listen
from grpclib.server import Server
from prometheus_async import aio
from sentry_sdk.integrations.aiohttp import AioHttpIntegration
from tortoise import Tortoise

from shadowsocks.proxyman import ProxyMan
from shadowsocks.rpc_clients import SSClient
from shadowsocks.services import AioShadowsocksServicer


async def logging_grpc_request(event: RecvRequest) -> None:
    logging.info(f"{event.method_name} called!")


class App:
    def __init__(self) -> None:
        self.loop = asyncio.get_event_loop()
        self._prepared = False

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

        self.use_sentry = bool(self.sentry_dsn)
        self.use_json = not self.api_endpoint
        self.metrics_server = None
        self.grpc_server = None

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
        level = log_levels[self.log_level.upper()]
        logging.basicConfig(
            format="[%(levelname)s]%(asctime)s %(funcName)s line:%(lineno)d %(message)s",
            level=level,
        )

    def _init_sentry(self):
        if not self.use_sentry:
            return
        sentry_sdk.init(dsn=self.sentry_dsn, integrations=[AioHttpIntegration()])
        logging.info("Init Sentry Client...")

    async def _init_memory_db(self):

        await Tortoise.init(
            db_url="sqlite://:memory:",
            modules={"models": ["shadowsocks.mdb.models"]},
        )

        # Generate the schema
        await Tortoise.generate_schemas()

    async def _prepare(self):
        if self._prepared:
            return
        self._init_config()
        self._init_logger()
        self._init_sentry()
        self.proxyman = ProxyMan(
            self.use_json, self.sync_time, self.listen_host, self.api_endpoint
        )

        await self._init_memory_db()

        signals = (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)
        for s in signals:
            self.loop.add_signal_handler(
                s, lambda s=s: asyncio.create_task(self._shutdown())
            )
        self._prepared = True

    async def _shutdown(self):
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        [task.cancel() for task in tasks]
        logging.info("正在关闭所有ss server")
        self.proxyman.close_server()
        if self.grpc_server:
            self.grpc_server.close()
            logging.info(f"grpc server closed!")
        if self.metrics_server:
            await self.metrics_server.stop()
            logging.info(f"metrics server closed!")
        await Tortoise.close_connections()

        self.loop.stop()

    async def _start_grpc_server(self):

        self.grpc_server = Server([AioShadowsocksServicer()], loop=self.loop)
        listen(self.grpc_server, RecvRequest, logging_grpc_request)
        await self.grpc_server.start(self.grpc_host, self.grpc_port)
        logging.info(f"Start grpc Server on {self.grpc_host}:{self.grpc_port}")

    async def _start_metrics_server(self):
        app = web.Application()
        app.router.add_get("/metrics", aio.web.server_stats)
        runner = web.AppRunner(app)
        await runner.setup()
        self.metrics_server = web.TCPSite(runner, "0.0.0.0", self.metrics_port)
        await self.metrics_server.start()
        logging.info(
            f"Start Metrics Server At: http://0.0.0.0:{self.metrics_port}/metrics"
        )

    async def _start_ss_server(self):
        await self._prepare()

        if self.metrics_port:
            await self._start_metrics_server()

        if self.grpc_host and self.grpc_port:
            await self._start_grpc_server()

        await self.proxyman.start_and_check_ss_server()

    def run_ss_server(self):
        self.loop.create_task(self._start_ss_server())
        self.loop.run_forever()

    def get_user(self, user_id):
        c = SSClient(f"{self.grpc_host}:{self.grpc_port}")
        return c.get_user(user_id)
