"""Access tokens (ISS-036; RS256 since spec 09 D5, ISS-073): signed with a private key, checked with
the public key, short-lived, naming only the user and tenant."""

import base64
import json
import time
import uuid

import jwt
import pytest

from app.auth import AuthError, TokenKeys, issue_token, key_id, verify_token
from app.config import Settings
from tests.keys import KEYS, pem_pair, token_keys

USER, TENANT = str(uuid.uuid4()), str(uuid.uuid4())


def _b64(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def test_a_token_round_trips_to_its_user_and_tenant() -> None:
    claims = verify_token(issue_token(USER, TENANT, keys=KEYS), keys=KEYS)
    assert (claims.user_id, claims.tenant_id) == (USER, TENANT)


def test_a_token_is_rs256_names_its_key_and_lasts_15_minutes() -> None:
    token = issue_token(USER, TENANT, keys=KEYS, now=1_800_000_000)
    header, payload = (
        jwt.get_unverified_header(token),
        jwt.decode(token, options={"verify_signature": False}),
    )
    assert header["alg"] == "RS256" and header["kid"] == key_id(pem_pair()[1])
    assert payload["exp"] - payload["iat"] == 900
    assert set(payload) == {"sub", "tenant", "iat", "exp"}  # no roles: those come from the DB


def test_an_expired_token_is_refused() -> None:
    token = issue_token(USER, TENANT, keys=KEYS, ttl_s=60, now=time.time() - 120)
    with pytest.raises(AuthError):
        verify_token(token, keys=KEYS)


def test_a_token_signed_with_another_key_is_refused() -> None:
    attacker = token_keys("attacker")
    forged = issue_token(USER, TENANT, keys=attacker)
    with pytest.raises(AuthError):
        verify_token(forged, keys=KEYS)  # unknown kid
    # Even claiming our key id, the signature doesn't match our public key.
    relabelled = jwt.encode(
        {"sub": USER, "tenant": TENANT, "exp": int(time.time()) + 60},
        pem_pair("attacker")[0],
        algorithm="RS256",
        headers={"kid": KEYS.signing_kid},
    )
    with pytest.raises(AuthError):
        verify_token(relabelled, keys=KEYS)


def test_a_tampered_payload_is_refused() -> None:
    header, _, signature = issue_token(USER, TENANT, keys=KEYS).split(".")
    other = _b64({"sub": str(uuid.uuid4()), "tenant": TENANT, "exp": int(time.time()) + 60})
    with pytest.raises(AuthError):
        verify_token(f"{header}.{other}.{signature}", keys=KEYS)


def test_an_unsigned_token_is_refused() -> None:
    unsigned = (
        f"{_b64({'alg': 'none', 'kid': KEYS.signing_kid})}."
        + _b64({"sub": USER, "tenant": TENANT, "exp": int(time.time()) + 60})
        + "."
    )
    with pytest.raises(AuthError):
        verify_token(unsigned, keys=KEYS)


def test_algorithm_confusion_is_refused() -> None:
    # The classic attack: sign with HS256 using the (public!) RSA key as the shared secret.
    header = _b64({"alg": "HS256", "typ": "JWT", "kid": KEYS.signing_kid})
    body = _b64({"sub": USER, "tenant": TENANT, "exp": int(time.time()) + 60})
    import hashlib
    import hmac

    mac = hmac.new(pem_pair()[1], f"{header}.{body}".encode(), hashlib.sha256).digest()
    forged = f"{header}.{body}.{base64.urlsafe_b64encode(mac).rstrip(b'=').decode()}"
    with pytest.raises(AuthError):
        verify_token(forged, keys=KEYS)


def test_garbage_is_refused() -> None:
    with pytest.raises(AuthError):
        verify_token("not-a-token", keys=KEYS)


def test_issuing_needs_the_private_key() -> None:
    check_only = TokenKeys.from_pems(None, pem_pair()[1])
    with pytest.raises(ValueError):
        issue_token(USER, TENANT, keys=check_only)
    verify_token(issue_token(USER, TENANT, keys=KEYS), keys=check_only)  # checking doesn't


def test_during_a_rotation_old_tokens_still_pass_and_new_ones_use_the_new_key() -> None:
    old_private, old_public = pem_pair("old")
    new_private, new_public = pem_pair("new")
    old_token = issue_token(USER, TENANT, keys=TokenKeys.from_pems(old_private, old_public))

    rotated = TokenKeys.from_pems(new_private, new_public, old_public)  # new first, old accepted

    assert verify_token(old_token, keys=rotated).user_id == USER
    assert jwt.get_unverified_header(issue_token(USER, TENANT, keys=rotated))["kid"] == key_id(
        new_public
    )


def test_keys_load_from_settings_as_base64_pem() -> None:
    private, public = pem_pair()
    settings = Settings(
        _env_file=None,
        jwt_private_key=base64.b64encode(private).decode(),
        jwt_public_key=base64.b64encode(public).decode(),
    )
    keys = TokenKeys.from_settings(settings)
    assert verify_token(issue_token(USER, TENANT, keys=keys), keys=KEYS).tenant_id == TENANT
    with pytest.raises(ValueError):
        TokenKeys.from_settings(
            Settings(_env_file=None, jwt_public_key="")
        )  # not this machine's .env


def test_a_token_claiming_a_long_life_is_refused() -> None:
    # Tester v0.9.0 T-6: a validly signed token with a one-year expiry used to pass.
    token = issue_token(USER, TENANT, keys=KEYS, ttl_s=365 * 86_400)
    with pytest.raises(AuthError):
        verify_token(token, keys=KEYS)
