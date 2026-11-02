"""S2 (ISS-036): access tokens — signed, expiring, and naming only the user and tenant."""

import time
import uuid

import jwt
import pytest

from app.auth import AuthError, issue_token, verify_token

SECRET = "test-secret-0123456789abcdef0123456789abcdef"
USER, TENANT = str(uuid.uuid4()), str(uuid.uuid4())


def test_a_token_round_trips_to_its_user_and_tenant() -> None:
    claims = verify_token(issue_token(USER, TENANT, secret=SECRET), secret=SECRET)
    assert (claims.user_id, claims.tenant_id) == (USER, TENANT)


def test_the_token_carries_no_roles() -> None:
    # Roles come from the database on every request, so removing one works immediately.
    payload = jwt.decode(issue_token(USER, TENANT, secret=SECRET), SECRET, algorithms=["HS256"])
    assert set(payload) == {"sub", "tenant", "iat", "exp"}


def test_an_expired_token_is_rejected() -> None:
    token = issue_token(USER, TENANT, secret=SECRET, ttl_s=60, now=time.time() - 120)
    with pytest.raises(AuthError):
        verify_token(token, secret=SECRET)


def test_a_token_signed_with_another_key_is_rejected() -> None:
    with pytest.raises(AuthError):
        verify_token(issue_token(USER, TENANT, secret="someone-else" * 4), secret=SECRET)


def test_a_tampered_token_is_rejected() -> None:
    header, payload, signature = issue_token(USER, TENANT, secret=SECRET).split(".")
    forged = jwt.encode({"sub": USER, "tenant": str(uuid.uuid4()), "exp": 9e9}, "x" * 32)
    with pytest.raises(AuthError):
        verify_token(f"{header}.{forged.split('.')[1]}.{signature}", secret=SECRET)


def test_an_unsigned_token_is_rejected() -> None:
    # The classic attack: "alg": "none" with no signature at all.
    unsigned = jwt.encode({"sub": USER, "tenant": TENANT, "exp": 9e9}, None, algorithm="none")
    with pytest.raises(AuthError):
        verify_token(unsigned, secret=SECRET)


@pytest.mark.parametrize(
    "payload",
    [
        {"tenant": TENANT, "exp": 9e9},  # no user
        {"sub": USER, "exp": 9e9},  # no tenant
        {"sub": USER, "tenant": TENANT},  # never expires
        {"sub": "alice", "tenant": TENANT, "exp": 9e9},  # not an id
    ],
)
def test_a_token_missing_a_claim_or_with_a_bad_id_is_rejected(payload) -> None:
    with pytest.raises(AuthError):
        verify_token(jwt.encode(payload, SECRET, algorithm="HS256"), secret=SECRET)


def test_garbage_is_rejected() -> None:
    with pytest.raises(AuthError):
        verify_token("not-a-token", secret=SECRET)


def test_an_empty_secret_is_refused() -> None:
    with pytest.raises(ValueError, match="JWT_SECRET"):
        issue_token(USER, TENANT, secret="")
