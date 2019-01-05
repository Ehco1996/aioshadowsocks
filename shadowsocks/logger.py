import logging


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
        format="[%(levelname)s] %(asctime)s - %(process)d - %(name)s - %(funcName)s() - %(message)s",  # noqa
        level=level,
    )
