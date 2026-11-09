"""Atomic Redis user/API-key and company request budgets."""

from __future__ import annotations

import re
from typing import Any, Protocol


_OPERATION = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_CHECK_TWO_BUCKETS = """
local actor = tonumber(redis.call('GET', KEYS[1]) or '0')
local company = tonumber(redis.call('GET', KEYS[2]) or '0')
if actor >= tonumber(ARGV[1]) or company >= tonumber(ARGV[2]) then
  local actor_ttl = redis.call('PTTL', KEYS[1])
  local company_ttl = redis.call('PTTL', KEYS[2])
  local ttl = math.max(actor_ttl, company_ttl, 1000)
  return {0, ttl}
end
actor = redis.call('INCR', KEYS[1])
if actor == 1 then redis.call('PEXPIRE', KEYS[1], ARGV[3]) end
company = redis.call('INCR', KEYS[2])
if company == 1 then redis.call('PEXPIRE', KEYS[2], ARGV[3]) end
return {1, 0}
"""


class RedisLike(Protocol):
    async def eval(self, script: str, numkeys: int, *keys_and_args: Any) -> Any: ...


class RedisRateLimiter:
    """One atomic decision across identity and tenant buckets.

    Keys contain only persisted UUIDs. Raw tokens and API keys never enter Redis.
    """

    def __init__(
        self,
        redis: RedisLike,
        *,
        actor_limit: int = 60,
        company_limit: int = 60,
        window_seconds: int = 60,
        namespace: str = "docusense:rate:v1",
    ) -> None:
        if redis is None:
            raise ValueError("Redis client is required")
        if actor_limit < 1 or company_limit < 1 or not 1 <= window_seconds <= 3600:
            raise ValueError("Invalid rate-limit budget")
        if not re.fullmatch(r"[a-z0-9:_-]{1,64}", namespace):
            raise ValueError("Invalid rate-limit namespace")
        self._redis = redis
        self._actor_limit = actor_limit
        self._company_limit = company_limit
        self._window_ms = window_seconds * 1000
        self._namespace = namespace

    async def check(self, caller: Any, operation: str = "shared") -> int | None:
        if not _OPERATION.fullmatch(operation):
            raise ValueError("Invalid rate-limit operation")
        company_id = getattr(caller, "company_id", None)
        user_id = getattr(caller, "user_id", None)
        api_key_id = getattr(caller, "api_key_id", None)
        if company_id is None or (user_id is None) == (api_key_id is None):
            raise ValueError("Caller has no unique persisted identity")
        kind, actor_id = ("user", user_id) if user_id is not None else ("api_key", api_key_id)
        prefix = f"{self._namespace}:{operation}"
        actor_key = f"{prefix}:actor:{kind}:{actor_id}"
        company_key = f"{prefix}:company:{company_id}"
        result = await self._redis.eval(
            _CHECK_TWO_BUCKETS,
            2,
            actor_key,
            company_key,
            self._actor_limit,
            self._company_limit,
            self._window_ms,
        )
        allowed, ttl_ms = int(result[0]), int(result[1])
        return None if allowed == 1 else max(1, (ttl_ms + 999) // 1000)


__all__ = ["RedisRateLimiter"]


