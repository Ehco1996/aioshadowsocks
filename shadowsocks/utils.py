import asyncio
import inspect
import logging
import socket
import struct

from grpclib.server import Server
from grpclib.utils import graceful_exit

from shadowsocks import protocol_flag as flag
from shadowsocks.services import AioShadowsocksServicer


def parse_header(data):
    atype, dst_addr, dst_port, header_length = None, None, None, 0
    try:
        atype = data[0]
    except IndexError:
        logging.warning("not valid data {}".format(data))

    if atype == flag.ATYPE_IPV4:
        if len(data) >= 7:
            dst_addr = socket.inet_ntop(socket.AF_INET, data[1:5])
            dst_port = struct.unpack("!H", data[5:7])[0]
            header_length = 7
        else:
            logging.warning("header is too short")
    elif atype == flag.ATYPE_IPV6:
        if len(data) >= 19:
            dst_addr = socket.inet_ntop(socket.AF_INET6, data[1:17])
            dst_port = struct.unpack("!H", data[17:19])[0]
            header_length = 19
        else:
            logging.warning("header is too short")
    elif atype == flag.ATYPE_DOMAINNAME:
        if len(data) > 2:
            addrlen = data[1]
            if len(data) >= 4 + addrlen:
                dst_addr = data[2 : 2 + addrlen]
                dst_port = struct.unpack("!H", data[2 + addrlen : addrlen + 4])[0]
                header_length = 4 + addrlen
            else:
                logging.warning("header is too short")
        else:
            logging.warning("header is too short")
    else:
        logging.warning("unknown atype: {} data: {}".format(atype, data))

    return atype, dst_addr, dst_port, header_length


def init_logger_config(log_level, open=True):
    """
    basic log config
    """
    log_levels = {"CRITICAL": 50, "ERROR": 40, "WARNING": 30, "INFO": 20, "DEBUG": 10}
    level = log_levels.get(log_level.upper(), 10)
    if open is False:
        logging.disable(level)
        return
    logging.basicConfig(
        format="[%(levelname)s] %(asctime)s - %(process)d - %(name)s - %(funcName)s() - %(message)s",
        level=level,
    )


def init_memory_db():
    from shadowsocks.mdb import models, BaseModel

    for _, model in inspect.getmembers(models, inspect.isclass):
        if issubclass(model, BaseModel) and model != BaseModel:
            model.create_table()
            logging.info(f"正在创建{model}临时数据库")


def start_ss_cron_job(sync_time, use_json=False):
    from shadowsocks.mdb.models import User, UserServer

    loop = asyncio.get_event_loop()
    try:
        if use_json:
            User.create_or_update_from_json("userconfigs.json")
        else:
            User.create_or_update_from_remote()
            UserServer.flush_data_to_remote()
        User.init_user_servers()
    except Exception as e:
        logging.warning(f"sync user error {e}")
    loop.call_later(sync_time, start_ss_cron_job, sync_time, use_json)


async def start_grpc_server(loop, host="0.0.0.0", port=5000):
    server = Server([AioShadowsocksServicer()], loop=loop)
    with graceful_exit([server], loop=loop):
        await server.start(host, port)
        logging.info(f"Start Grpc Server on {host}:{port}")
        await server.wait_closed()
