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

        self.__dict__.update(propertys)

    def __repr__(self):
        return '<shdowsocks user object user_id:{}>'.format(self.user_id)

    @property
    def used_traffic(self):
        return self.upload_traffic + self.download_traffic
