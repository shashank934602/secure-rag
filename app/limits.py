"""Rate limits and the daily token budget (spec 09 D2–D4, D7; ISS-072).

    rate limit     fixed one-minute windows: per user, then per tenant → 429 + Retry-After
    token budget   tokens a tenant's answers used today (UTC); at the budget → 429 until midnight.
                   Each question first *reserves* tokens in one atomic step (so simultaneous
                   questions can't all slip under the budget, tester v0.9.0 T-2), then the
                   reservation is corrected to what the answer really used.

Counters live in Redis (`REDIS_URL`) so several API processes share them; without it an in-memory
counter is used, which is correct for one process (development, tests). If the counter store
can't be reached the request is refused (LimiterUnavailable → 503): a limit that silently stops
working is worse than none, because nobody notices.
"""

import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from app.domain import User

MINUTE = 60
DAY = 86_400


class LimitExceeded(Exception):
    def __init__(self, detail: str, retry_after_s: int) -> None:
        super().__init__(detail)
        self.detail, self.retry_after_s = detail, max(1, retry_after_s)


class LimiterUnavailable(Exception):
    """The counter store failed: the caller must refuse the request (fail closed)."""


class Counter(Protocol):
    def incr(self, key: str, amount: int, ttl_s: int) -> int:
        """Add `amount` to `key` (creating it with a time-to-live) and return the new total."""
        ...

    def get(self, key: str) -> int: ...


class MemoryCounter:
    """Counters in this process's memory, with expiry. One process only."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._values: dict[str, tuple[int, float]] = {}
        self._lock, self._clock = threading.Lock(), clock

    def incr(self, key: str, amount: int, ttl_s: int) -> int:
        with self._lock:
            now = self._clock()
            value, expires = self._values.get(key, (0, now + ttl_s))
            if expires <= now:
                value, expires = 0, now + ttl_s
            self._values[key] = (value + amount, expires)
            return value + amount

    def get(self, key: str) -> int:
        with self._lock:
            value, expires = self._values.get(key, (0, 0.0))
            return value if expires > self._clock() else 0


class RedisCounter:
    """Counters in Redis: shared by every API process. Errors become LimiterUnavailable."""

    def __init__(self, url: str) -> None:
        import redis  # only when Redis is configured

        self._redis = redis.Redis.from_url(url, socket_timeout=1.0, socket_connect_timeout=1.0)

    def incr(self, key: str, amount: int, ttl_s: int) -> int:
        try:
            pipe = self._redis.pipeline()
            pipe.incrby(key, amount)
            pipe.expire(key, ttl_s, nx=True)  # set the lifetime once, when the key is created
            total, _ = pipe.execute()
            return int(total)
        except Exception as error:
            raise LimiterUnavailable(type(error).__name__) from error

    def get(self, key: str) -> int:
        try:
            value = self._redis.get(key)
        except Exception as error:
            raise LimiterUnavailable(type(error).__name__) from error
        return int(value or 0)


class Limits:
    def __init__(
        self,
        counter: Counter,
        *,
        per_user_per_min: int,
        per_tenant_per_min: int,
        tenant_daily_tokens: int,
        reservation: int = 6000,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.counter, self.clock = counter, clock
        self.per_user, self.per_tenant = per_user_per_min, per_tenant_per_min
        self.budget, self.reservation = tenant_daily_tokens, reservation

    def check_rate(self, user: User) -> None:
        """Count this request; raise LimitExceeded if the user or the tenant is over its limit."""
        now = self.clock()
        window, retry = int(now // MINUTE), MINUTE - int(now % MINUTE)
        if self._count(f"rl:user:{user.id}:{window}") > self.per_user:
            raise LimitExceeded(f"Too many requests: at most {self.per_user} a minute", retry)
        if self._count(f"rl:tenant:{user.tenant_id}:{window}") > self.per_tenant:
            raise LimitExceeded(
                "Too many requests from your organisation; try again shortly", retry
            )

    def reserve(self, user: User) -> int:
        """Book tokens for one answer before any model call; LimitExceeded if the tenant had
        already used today's budget. Returns the amount booked (settle it afterwards)."""
        key = self._budget_key(user)
        after = self.counter.incr(key, self.reservation, 2 * DAY)  # one atomic step
        if after - self.reservation >= self.budget:
            self.counter.incr(key, -self.reservation, 2 * DAY)  # give the booking back
            raise LimitExceeded(
                "Your organisation's daily usage limit is reached", self._to_midnight()
            )
        return self.reservation

    def settle(self, user: User, reserved: int, used: int) -> None:
        """Correct a booking to what the answer really used (0 if it failed before answering)."""
        if used != reserved:
            self.counter.incr(self._budget_key(user), used - reserved, 2 * DAY)

    def ping(self) -> None:
        """Raise LimiterUnavailable if the counter store can't be reached (health check)."""
        self.counter.get("health:ping")

    def _count(self, key: str) -> int:
        return self.counter.incr(key, 1, 2 * MINUTE)

    def _budget_key(self, user: User) -> str:
        day = datetime.fromtimestamp(self.clock(), UTC).strftime("%Y-%m-%d")
        return f"budget:{user.tenant_id}:{day}"

    def _to_midnight(self) -> int:
        return DAY - int(self.clock() % DAY)


class NoLimits:
    """No limits at all: only for the offline eval runs, never the API's default."""

    def check_rate(self, user: User) -> None: ...
    def reserve(self, user: User) -> int:
        return 0

    def settle(self, user: User, reserved: int, used: int) -> None: ...
    def ping(self) -> None: ...


def total_tokens(usage: dict[str, dict[str, int]]) -> int:
    return sum(counts.get("total_tokens", 0) for counts in usage.values())


def build_limits(settings) -> Limits:
    counter = RedisCounter(settings.redis_url) if settings.redis_url else MemoryCounter()
    return Limits(
        counter,
        per_user_per_min=settings.rate_limit_user_per_min,
        per_tenant_per_min=settings.rate_limit_tenant_per_min,
        tenant_daily_tokens=settings.tenant_daily_token_budget,
    )
