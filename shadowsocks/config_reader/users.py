'''
user object
'''


class User:
    def __init__(self, **propertys):

        self.upload_traffic = 0
        self.download_traffic = 0
        self.total_traffic = 0
        self.peername = None
        self.user_id = None

        # 记录每次同步间隔间的力量
        self.once_used_u = 0
        self.once_used_d = 0

        self.__dict__.update(propertys)

    def __repr__(self):
        return '<shdowsocks user object user_id:{}>'.format(self.user_id)

    @property
    def used_traffic(self):
        return self.upload_traffic + self.download_traffic

    @property
    def human_used_traffic(self):
        return self._traffic_format(self.used_traffic)

    def _traffic_format(self, traffic):
        if traffic < 1024 * 8:
            return str(int(traffic)) + "B"

        if traffic < 1024 * 1024:
            return str(round((traffic / 1024.0), 2)) + "KB"

        if traffic < 1024 * 1024 * 1024:
            return str(round((traffic / (1024.0 * 1024)), 2)) + "MB"

        return str(round((traffic / 1073741824.0), 2)) + "GB"
