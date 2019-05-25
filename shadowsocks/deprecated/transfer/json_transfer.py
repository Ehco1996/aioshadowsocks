import json
import logging


class JsonTransfer:
    def __init__(self, path):
        self.path = path
        self.local_address = "0.0.0.0"

    def get_all_user_configs(self):
        """
        拉取符合要求的用户信息
        """
        with open(self.path, "r") as f:
            data = json.load(f)
        if not data["users"]:
            logging.warning("没有查询到满足要求的user，请检查自己的config")
            return
        return data["users"]

    def update_all_user(self, user_list):
        """
        更新user信息，上报用户流量
        """
        data = []
        for user in user_list:
            data.append(
                {"user_id": user.user_id, "u": user.once_used_u, "d": user.once_used_d}
            )
            # reset user used traffic
            user.once_used_u = 0
            user.once_used_d = 0
