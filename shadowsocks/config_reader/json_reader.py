import json

from shadowsocks.config_reader.users import User


def json_config_reader(path):
    '''
    读取`json`中的userconfig
    '''
    with open(path, 'r') as f:
        data = json.load(f)
    objs = list()
    for user in data['users']:
        objs.append(User(**user))
    data['users'] = objs
    return data
