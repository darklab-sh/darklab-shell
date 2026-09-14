# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Classify idle Redis stream reads without hiding transport failures."""

from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError


def is_redis_idle_timeout_error(exc: BaseException) -> bool:
    if isinstance(exc, RedisTimeoutError):
        return True
    if isinstance(exc, RedisConnectionError):
        message = str(exc).lower()
        return "timeout reading" in message or "timed out" in message
    return False
