import logging


def init_logger_config():
    logging.basicConfig(
        format='[%(levelname)s] %(asctime)s - %(process)d - %(name)s - %(funcName)s() - %(message)s',  # noqa
        level=logging.INFO)
