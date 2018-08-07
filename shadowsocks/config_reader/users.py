'''
user object
'''


class User:
    def __init__(self, **propertys):
        self.__dict__.update(propertys)

        self.upload_traffic = 0
        self.download_traffic = 0
        self.peername = None

    def __repr__(self):
        return '<shdowsocks user object user_id:{}>'.format(self.user_id)
