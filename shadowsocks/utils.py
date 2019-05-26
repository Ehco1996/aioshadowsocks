import logging
import socket
import struct
import inspect

from shadowsocks import protocol_flag as flag


def parse_header(data):
    atype, dst_addr, dst_port, header_length = None, None, None, 0
    try:
        atype = data[0]
    except IndexError:
        logging.warning("not vaild data {}".format(data))

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
