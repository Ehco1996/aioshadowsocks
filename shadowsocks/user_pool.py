class User:
    def __init__(self, **properties):

        self.upload_traffic = 0
        self.download_traffic = 0
        self.total_traffic = 0
        self.peername = None
        self.user_id = None
        self.obfs = None
        self.obfs_param = None
        self.token = None

        # 记录每次同步间隔间的流量
        self.once_used_u = 0
        self.once_used_d = 0

        # 活跃的tcp连接数
        self.tcp_count = 0
        self.ip_list = set()

        self.__dict__.update(properties)

        # format for api
        if "passwd" in properties:
            self.password = properties["passwd"]
        if "id" in properties:
            self.user_id = properties["id"]
        if "u" in properties:
            self.upload_traffic = properties["u"]
        if "d" in properties:
            self.download_traffic = properties["d"]
        if "transfer_enable" in properties:
            self.total_traffic = properties["transfer_enable"]

    def __repr__(self):
        return f"<user_id:{self.user_id}>"

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

        return str(round((traffic / 1_073_741_824.0), 2)) + "GB"


class UserPool:
    _instance = None

    # user_id:user object
    USER_MAP = dict()

    # index: token -> user_id
    TOKEN_ID_MAP = dict()

    def __new__(cls, *args, **kw):
        if not cls._instance:
            cls._instance = super(UserPool, cls).__new__(cls, *args, **kw)
        return cls._instance

    @classmethod
    def add_user(cls, user):
        cls.USER_MAP[user.user_id] = user
        cls.TOKEN_ID_MAP[user.token] = user.user_id

    @classmethod
    def get_by_user_id(cls, user_id):
        return cls.USER_MAP[user_id]

    @classmethod
    def get_by_token(cls, token):
        user_id = cls.TOKEN_ID_MAP[token]
        return cls.get_by_user_id(user_id)

    @classmethod
    def get_user_list(cls):
        return list(cls.USER_MAP.values())

    @classmethod
    def remove_user_by_user_id(cls, user_id):
        if user_id in cls.USER_MAP:
            user = cls.USER_MAP.pop(user_id)
            cls.TOKEN_ID_MAP.pop(user.token)
