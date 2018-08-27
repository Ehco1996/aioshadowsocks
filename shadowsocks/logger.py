import logging


def init_logger_config(log_level):
    '''
    basic log config
    '''
    log_levels = {'CRITICAL': 50,
                  "ERROR": 40,
                  "WARNING": 30,
                  "INFO": 20,
                  "DEBUG": 10}
    level = log_levels.get(log_level.upper(), 10)
    logging.basicConfig(
        format='[%(levelname)s] %(asctime)s - %(process)d - %(name)s - %(funcName)s() - %(message)s',  # noqa
        level=level)
