'''
user object
'''

class User:
    def __init__(self, **propertys):
        self.__dict__.update(propertys)
