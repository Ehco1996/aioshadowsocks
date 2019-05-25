import peewee as pw
from playhouse import shortcuts

db = pw.SqliteDatabase(":memory:")


class BaseModel(pw.Model):
    __attr_protected__ = set()

    class Meta:
        database = db

    def update_from_dict(self, data, ignore_unknown=False):
        """注意值是没有写入数据库的, 需要显式 save"""
        clean_data = {
            k: v
            for k, v in data.items()
            if k in self._meta.fields and k not in self.__attr_protected__
        }
        return shortcuts.update_model_from_dict(self, clean_data, ignore_unknown)

    def to_dict(self):
        return shortcuts.model_to_dict(self)
