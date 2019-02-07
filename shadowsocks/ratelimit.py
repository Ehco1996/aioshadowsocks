import sys
import time
import threading
from math import floor
from functools import wraps


class RateLimitException(Exception):
    """
    Rate limit exception class.
    """

    def __init__(self, message, period_remaining):
        super(RateLimitException, self).__init__(message)
        self.period_remaining = period_remaining


class UserRateLimitDecorator:
    LIMITS_MAP = {}
    USER_LIMIT_CONFIG = {"calls": 15, "period": 900, "raise_on_limit": True}

    def __init__(self, user_id=None, calls=15, period=900, raise_on_limit=True):
        if not user_id:
            self.USER_LIMIT_CONFIG["calls"] = calls
            self.USER_LIMIT_CONFIG["period"] = period
            self.USER_LIMIT_CONFIG["raise_on_limit"] = raise_on_limit
            return
        else:
            self.clamped_calls = max(1, min(sys.maxsize, floor(calls)))
            self.period = period
            self.clock = time.monotonic if hasattr(time, "monotonic") else time.time
            self.raise_on_limit = raise_on_limit

            # Initialise the decorator state.
            self.last_reset = self.clock()
            self.num_calls = 0

            # Add thread safety.
            self.lock = threading.RLock()
            self.LIMITS_MAP[user_id] = self

    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kargs):
            user_id = args[0].user.user_id
            limit = self.LIMITS_MAP.get(user_id)
            if not limit:
                self.__init__(
                    user_id,
                    self.USER_LIMIT_CONFIG["calls"],
                    self.USER_LIMIT_CONFIG["period"],
                    self.USER_LIMIT_CONFIG["raise_on_limit"],
                )
                limit = self.LIMITS_MAP[user_id]
            with limit.lock:
                period_remaining = limit.__period_remaining()

                # If the time window has elapsed then reset.
                if period_remaining <= 0:
                    limit.num_calls = 0
                    limit.last_reset = limit.clock()

                # Increase the number of attempts to call the function.
                limit.num_calls += 1

                # If the number of attempts to call the function exceeds the
                # maximum then raise an exception.
                if limit.num_calls > limit.clamped_calls:
                    if limit.raise_on_limit:
                        raise RateLimitException(
                            f"user:{user_id}too many calls period:{period_remaining}",
                            period_remaining,
                        )
                    return

            return func(*args, **kargs)

        return wrapper

    def __period_remaining(self):
        elapsed = self.clock() - self.last_reset
        return self.period - elapsed
