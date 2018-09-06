import gc
import json
import logging
import traceback

import requests
from requests.adapters import Retry
from requests.adapters import HTTPAdapter

from transfer.users import User


def json_config_reader(path):
    '''
    读取`json`中的userconfig
    '''
    with open(path, 'r') as f:
        data = json.load(f)
    objs = list()
    for user in data['users']:
        user = User(**user)
        if user.enable is True:
            objs.append(user)
    data['users'] = objs
    return data


class EhcoApi:
    '''
    提供发送get/post的抽象类
    '''

    def __init__(self, token, url):
        self.TOKEN = token
        self.WEBAPI_URL = url

        self.session = requests.Session()
        http_adapter = HTTPAdapter(max_retries=Retry(
            total=3, method_whitelist=frozenset(['GET', 'POST'])))
        self.session.mount('https://', http_adapter)

    def getApi(self, uri):
        res = None
        try:
            payload = {'token': self.TOKEN}
            url = self.WEBAPI_URL+uri
            res = self.session.get(url, params=payload, timeout=10)
            try:
                data = res.json()
            except Exception:
                if res:
                    logging.error('接口返回值格式错误: {}'.format(res.text))
                return []

            if data['ret'] == -1:
                logging.error("接口返回值不正确:{}".format(res.text))
                logging.error("请求头：{}".format(uri))
                return []
            return data['data']

        except Exception:
            trace = traceback.format_exc()
            logging.error(trace)
            logging.error(
                '网络问题，请保证api接口地址设置正确！当前接口地址：{}'.format(self.WEBAPI_URL))

    def postApi(self, uri, raw_data={}):
        res = None
        try:
            payload = {'token': self.TOKEN}
            payload.update(raw_data)
            url = self.WEBAPI_URL+uri
            res = self.session.post(url, json=payload, timeout=10)
            try:
                data = res.json()
            except Exception:
                if res:
                    logging.error('接口返回值格式错误: {}'.format(res.text))
                return []
            if data['ret'] == -1:
                logging.error("接口返回值不正确:{}".format(res.text))
                logging.error("请求头：{}".format(uri))
                return []
            return data['data']
        except Exception:
            trace = traceback.format_exc()
            logging.error(trace)
            logging.error(
                '网络问题，请保证api接口地址设置正确！当前接口地址：{}'.format(self.WEBAPI_URL))


def get_obj_by_id(obj_id):
    for obj in gc.get_objects():
        if id(obj) == obj_id:
            return obj
