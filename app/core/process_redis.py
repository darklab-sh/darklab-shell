"""Redis process-state helpers."""

from __future__ import annotations

from typing import Any


class RedisClientProxy:
    """Proxy process-level Redis state so monkeypatches stay visible at call time."""

    def _client(self) -> Any | None:
        from core import process

        return process.redis_client

    def __bool__(self) -> bool:
        return bool(self._client())

    def __getattr__(self, name: str) -> Any:
        client = self._client()
        if client is None:
            raise AttributeError(name)
        return getattr(client, name)
