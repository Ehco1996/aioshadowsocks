import logging

import peewee as pw
import requests
from playhouse import shortcuts

db = pw.SqliteDatabase(":memory:")


class BaseModel(pw.Model):
    __attr_protected__ = set()
    __attr_accessible__ = set()

    class Meta:
        database = db

    @classmethod
    def _filter_attrs(cls, attrs, use_whitelist=True):
        if use_whitelist:
            whitelist = cls.__attr_accessible__ - cls.__attr_protected__
            return {k: v for k, v in attrs.items() if k in whitelist}
        else:
            blacklist = cls.__attr_protected__ - cls.__attr_accessible__
            return {k: v for k, v in attrs.items() if k not in blacklist}

    @classmethod
    def get_or_create(cls, **kw):
        if "defaults" in kw:
            kw["defaults"] = cls._filter_attrs(kw.pop("defaults"))
        return super().get_or_create(**kw)

    def update_from_dict(self, data, ignore_unknown=False, use_whitelist=False):
        """注意值是没有写入数据库的, 需要显式 save"""
        cls = type(self)
        clean_data = cls._filter_attrs(data)
        return shortcuts.update_model_from_dict(self, clean_data, ignore_unknown)

    def to_dict(self, **kw):
        return shortcuts.model_to_dict(self, **kw)


class HttpSession:
    def __init__(self):
        self.session = requests.Session()

    def request(self, method, url, **kw):
        req_method = getattr(self.session, method)
        try:
            logging.debug(f"url: {url},method: {method},kw: {kw}")
            return req_method(url, **kw)
        except (requests.exceptions.HTTPError, requests.exceptions.MissingSchema) as e:
            logging.warning(f"请求错误 url:{url} error: {e}")


class HttpSessionMixin:

    http_session = HttpSession()
