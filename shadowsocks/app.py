import asyncio
import inspect
import logging
import os
import signal

import raven
import uvloop
from grpclib.server import Server
from raven_aiohttp import AioHttpTransport

from shadowsocks.mdb import BaseModel, models
from shadowsocks.services import AioShadowsocksServicer


class App:
    def __init__(self):
        uvloop.install()
        self.loop = asyncio.get_event_loop()
        self.loop.add_signal_handler(signal.SIGTERM, self.shutdown)

        self.config = {
            "API_ENDPOINT": os.getenv("SS_API_ENDPOINT"),
            "GRPC_HOST": os.getenv("SS_GRPC_HOST"),
            "GRPC_PORT": os.getenv("SS_GRPC_PORT"),
            "SYNC_TIME": int(os.getenv("SS_SYNC_TIME", 60)),
            "LOG_LEVEL": os.getenv("SS_LOG_LEVEL", "info"),
            "SENTRY_DSN": os.getenv("SS_SENTRY_DSN"),
        }

        self.api_endpoint = self.config["API_ENDPOINT"]
        self.grpc_host = self.config["GRPC_HOST"]
        self.grpc_port = self.config["GRPC_PORT"]
        self.sentry_dsn = self.config["SENTRY_DSN"]

        self.use_json = False if self.api_endpoint else True
        self.use_grpc = True if self.grpc_host and self.grpc_port else False
        self.use_sentry = True if self.sentry_dsn else False

        self._prepared = False

    def _init_logger_config(self):
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
        level = log_levels.get(self.config["LOG_LEVEL"].upper(), 10)
        logging.basicConfig(
            format="[%(levelname)s]%(asctime)s-%(name)s - %(funcName)s() - %(message)s",
            level=level,
        )

    def _init_memory_db(self):
        for _, model in inspect.getmembers(models, inspect.isclass):
            if issubclass(model, BaseModel) and model != BaseModel:
                model.create_table()
                logging.info(f"正在创建{model}临时数据库")

    def __sentry_exception_handler(self, loop, context):
        try:
            raise context["exception"]
        except TimeoutError:
            logging.error(f"socket timeout msg: {context['message']}")
        except Exception:
            logging.error(f"unhandled error msg: {context['message']}")
            self.sentry_client.captureException(**context)

    def _init_sentry_client(self):
        self.sentry_client = raven.Client(self.sentry_dsn, transport=AioHttpTransport)
        self.loop.set_exception_handler(self.__sentry_exception_handler)
        logging.info("Init Sentry Client...")

    def _prepare(self):
        if self._prepared:
            return
        self._init_logger_config()
        self._init_memory_db()
        self.use_sentry and self._init_sentry_client()
        self._prepared = True

    def start_json_server(self):
        models.User.create_or_update_from_json("userconfigs.json")
        models.User.init_user_servers()

    def start_remote_sync_server(self):
        try:
            models.User.create_or_update_from_remote(self.api_endpoint)
            models.UserServer.flush_data_to_remote(self.api_endpoint)
            models.User.init_user_servers()
        except Exception as e:
            logging.warning(f"sync user error {e}")
        self.loop.call_later(self.config["SYNC_TIME"], self.start_remote_sync_server)

    async def start_grpc_server(self):
        self.grpc_server = Server([AioShadowsocksServicer()], loop=self.loop)
        await self.grpc_server.start(self.grpc_host, self.grpc_port)
        logging.info(f"Start Grpc Server on {self.grpc_host}:{self.grpc_port}")

    def shutdown(self):
        models.UserServer.shutdown()
        if self.use_grpc:
            self.grpc_server.close()
            logging.info(f"Grpc Server on {self.grpc_host}:{self.grpc_port} Closed!")

        self.loop.stop()

    def run(self):
        self._prepare()

        if self.use_json:
            self.start_json_server()
        else:
            self.start_remote_sync_server()

        if self.use_grpc:
            self.loop.create_task(self.start_grpc_server())

        try:
            self.loop.run_forever()
        except KeyboardInterrupt:
            logging.info("正在关闭所有ss server")
            self.shutdown()
