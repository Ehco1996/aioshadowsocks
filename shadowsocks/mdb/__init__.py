import json
from typing import Set

from tortoise import fields
from tortoise.models import Model


class BaseModel(Model):
    __attr_protected__ = set()
    __attr_accessible__ = set()

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

    async def update_from_dict(self, data, use_whitelist=False):
        cls = type(self)
        clean_data = cls._filter_attrs(data, use_whitelist)
        return await super().update_from_dict(clean_data)

    def to_dict(self):
        return self.dict()


class IPSetField(fields.CharField):
    def to_db_value(self, value, instance) -> str:
        if type(value) is not set:
            value = []
        data = json.dumps(list(value))
        if len(data) > self.max_length:
            raise ValueError("Data too long for field {}.".format(self.name))
        return data

    def to_python_value(self, value) -> Set[str]:
        if value is None:
            return value
        l = json.loads(value)
        return set(l)
