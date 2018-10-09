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

        # 记录每次同步间隔间的流量
        self.once_used_u = 0
        self.once_used_d = 0

        # user_ip
        self.user_ip = None
        # 活跃的tcp连接数
        self.tcp_count = 0

        self.__dict__.update(propertys)

        # format for api
        if 'passwd' in propertys:
            self.password = propertys['passwd']
        if 'id' in propertys:
            self.user_id = propertys['id']
        if 'u' in propertys:
            self.upload_traffic = propertys['u']
        if 'd' in propertys:
            self.download_traffic = propertys['d']
        if 'transfer_enable' in propertys:
            self.total_traffic = propertys['transfer_enable']

    def __repr__(self):
        return '<shdowsocks user object user_id:{}>'.format(self.user_id)

    @property
    def used_traffic(self):
        return self.upload_traffic + self.download_traffic

    @property
    def human_used_traffic(self):
        return self._traffic_format(self.used_traffic)

    @property
    def once_used_traffic(self):
        return self.once_used_u + self.once_used_d

    @property
    def enable(self):
        if self.used_traffic < self.total_traffic:
            return True
        else:
            return False

    def _traffic_format(self, traffic):
        if traffic < 1024 * 8:
            return str(int(traffic)) + "B"

        if traffic < 1024 * 1024:
            return str(round((traffic / 1024.0), 2)) + "KB"

        if traffic < 1024 * 1024 * 1024:
            return str(round((traffic / (1024.0 * 1024)), 2)) + "MB"

        return str(round((traffic / 1073741824.0), 2)) + "GB"
