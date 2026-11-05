"""Rate limits and the daily token budget (spec 09 D2–D4, D7; ISS-072). Offline."""

import pytest
from fastapi.testclient import TestClient

from app.audit.recorder import NullRecorder
from app.domain import User
from app.limits import LimiterUnavailable, LimitExceeded, Limits, MemoryCounter
from app.main import create_app
from tests.test_api import ALICE, _answerer, _authenticate

BOB = User(id="u-bob", tenant_id="t-aldermoor", email="bob@x", roles=["employee"], permissions=[])
NED = User(id="u-ned", tenant_id="t-northgate", email="ned@x", roles=["employee"], permissions=[])


class Clock:
    def __init__(self, now: float = 1_800_000_000.0) -> None:  # a fixed instant, mid-minute
        self.now = now

    def __call__(self) -> float:
        return self.now


def _limits(clock: Clock, user: int = 2, tenant: int = 100, budget: int = 1000) -> Limits:
    return Limits(
        MemoryCounter(clock),
        per_user_per_min=user,
        per_tenant_per_min=tenant,
        tenant_daily_tokens=budget,
        clock=clock,
    )


def test_a_user_over_the_limit_is_refused_until_the_next_minute() -> None:
    clock = Clock()
    limits = _limits(clock, user=2)
    limits.check_rate(ALICE)
    limits.check_rate(ALICE)

    with pytest.raises(LimitExceeded) as refused:
        limits.check_rate(ALICE)
    assert 1 <= refused.value.retry_after_s <= 60

    limits.check_rate(BOB)  # another user isn't affected
    clock.now += 60  # next window
    limits.check_rate(ALICE)


def test_a_tenant_limit_covers_all_its_users_but_not_other_tenants() -> None:
    limits = _limits(Clock(), user=10, tenant=3)
    for user in (ALICE, BOB, ALICE):
        limits.check_rate(user)
    with pytest.raises(LimitExceeded):
        limits.check_rate(BOB)
    limits.check_rate(NED)


def test_the_token_budget_stops_a_tenant_until_midnight_utc() -> None:
    clock = Clock()
    limits = _limits(clock, budget=1000)
    limits.check_budget(ALICE)
    limits.spend(ALICE, 1000)

    with pytest.raises(LimitExceeded) as refused:
        limits.check_budget(BOB)  # same tenant: same budget
    assert refused.value.retry_after_s == 86_400 - int(clock.now % 86_400)
    limits.check_budget(NED)  # other tenant unaffected

    clock.now += refused.value.retry_after_s  # midnight UTC
    limits.check_budget(ALICE)


# --- through the API ---------------------------------------------------------------------------


def _client(limits) -> TestClient:
    app = create_app(
        build=lambda: _answerer(*["I don't know based on the documents I can access."] * 5),
        health_check=lambda: None,
        recorder=NullRecorder,
        authenticator=lambda: _authenticate,
        limits=lambda: limits,
    )
    return TestClient(app, headers={"Authorization": "Bearer good-token"})


def test_the_api_answers_429_with_retry_after_when_a_user_floods_it() -> None:
    with _client(_limits(Clock(), user=2)) as client:
        codes = [client.post("/v1/ask", json={"question": "Leave?"}).status_code for _ in range(3)]
        refused = client.post("/v1/ask", json={"question": "Leave?"})

    assert codes == [200, 200, 429]
    assert int(refused.headers["retry-after"]) >= 1
    assert "at most 2 a minute" in refused.json()["detail"]


def test_a_tenant_past_its_budget_gets_429_and_no_model_call() -> None:
    limits = _limits(Clock(), budget=10)
    limits.spend(ALICE, 10)
    answerer = _answerer()  # no scripted replies: any model call would fail
    app = create_app(
        build=lambda: answerer,
        health_check=lambda: None,
        recorder=NullRecorder,
        authenticator=lambda: _authenticate,
        limits=lambda: limits,
    )
    with TestClient(app, headers={"Authorization": "Bearer good-token"}) as client:
        response = client.post("/v1/ask", json={"question": "How much leave?"})

    assert response.status_code == 429 and "daily usage limit" in response.json()["detail"]
    assert answerer.chat_model.calls == []


def test_a_broken_limiter_refuses_instead_of_serving_unlimited() -> None:
    class Down:
        def check_rate(self, user):
            raise LimiterUnavailable("ConnectionError")

    with _client(Down()) as client:
        response = client.post("/v1/ask", json={"question": "Leave?"})
        audit = client.get("/v1/audit/verify")
    assert (response.status_code, audit.status_code) == (503, 503)


def test_rate_limits_cover_every_authenticated_route() -> None:
    with _client(_limits(Clock(), user=1)) as client:
        client.get("/v1/audit/verify")  # the first request of the minute (403 for alice)
        second = client.patch("/v1/documents/leave-policy/acl", json={"allowed_roles": ["hr"]})
    assert second.status_code == 429
