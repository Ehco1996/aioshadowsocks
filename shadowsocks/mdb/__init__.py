import json
from typing import Set

import peewee as pw
import requests
from playhouse import shortcuts

# NOTE 需要自己做线程安全
db = pw.SqliteDatabase(":memory:", thread_safe=False, check_same_thread=False)


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


class IPSetField(pw.CharField):
    def db_value(self, value) -> str:
        if type(value) is not set:
            value = []
        data = json.dumps(list(value))
        if len(data) > self.max_length:
            raise ValueError("Data too long for field {}.".format(self.name))
        return data

    def python_value(self, value) -> Set[str]:
        if value is None:
            return value
        l = json.loads(value)
        return set(l)


class HttpSession:
    def __init__(self):
        self.session = requests.Session()

    def request(self, method, url, **kw):
        req_method = getattr(self.session, method)
        return req_method(url, **kw)


class HttpSessionMixin:

    http_session = HttpSession()
