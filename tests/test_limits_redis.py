"""The Redis-backed limiter (spec 09 D2, D4; ISS-072): shared counts, expiry, and fail closed.

Needs Docker:   uv run pytest -m db
"""

import time

import pytest

from app.domain import User
from app.limits import LimiterUnavailable, LimitExceeded, Limits, RedisCounter

pytestmark = pytest.mark.db
REDIS_IMAGE = "redis:7.2.7-alpine"  # same as docker-compose.yml
ALICE = User(id="u-a", tenant_id="t-1", email="a@x", roles=["employee"], permissions=[])


@pytest.fixture
def redis_url():
    from testcontainers.community.redis import RedisContainer

    with RedisContainer(REDIS_IMAGE) as container:
        host, port = container.get_container_host_ip(), container.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0", container


def _limits(url: str, per_user: int = 2) -> Limits:
    return Limits(
        RedisCounter(url),
        per_user_per_min=per_user,
        per_tenant_per_min=100,
        tenant_daily_tokens=1000,
    )


def test_two_api_processes_share_one_count(redis_url) -> None:
    url, _ = redis_url
    first, second = _limits(url), _limits(url)  # as if two API processes
    first.check_rate(ALICE)
    second.check_rate(ALICE)
    with pytest.raises(LimitExceeded):
        first.check_rate(ALICE)


def test_counters_expire_on_their_own(redis_url) -> None:
    url, _ = redis_url
    counter = RedisCounter(url)
    assert counter.incr("k", 5, ttl_s=1) == 5
    assert counter.incr("k", 1, ttl_s=1) == 6  # the lifetime is set once, not extended
    time.sleep(1.5)
    assert counter.get("k") == 0


def test_the_budget_is_shared_through_redis(redis_url) -> None:
    url, _ = redis_url
    first = _limits(url)
    first.settle(ALICE, first.reserve(ALICE), 1000)
    with pytest.raises(LimitExceeded):
        _limits(url).reserve(ALICE)


def test_redis_down_means_refuse_not_unlimited(redis_url) -> None:
    url, container = redis_url
    limits = _limits(url)
    container.get_wrapped_container().stop()  # Redis goes away; the fixture still cleans up
    with pytest.raises(LimiterUnavailable):
        limits.check_rate(ALICE)
    with pytest.raises(LimiterUnavailable):
        limits.reserve(ALICE)
    with pytest.raises(LimiterUnavailable):
        limits.ping()
