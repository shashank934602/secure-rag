"""Authentication (spec 04 D5; RS256 since spec 09 D5): a signed token says who you are; the
database says what you may see.

    uv run python -m app.auth token --tenant Aldermoor --email alice@aldermoor.example.com

The token holds only the user id (`sub`), the tenant id, and a short expiry (15 minutes). Roles and
permissions are loaded from the database on every request, inside that tenant's scope, so a removed
role takes effect at once and a token can never reach a user of another tenant (row-level security).

Tokens are signed with a private key (RS256) and checked with the public key: whatever only checks
tokens never holds the key that makes them. The header names the key (`kid`), so a new key can be
introduced while tokens signed with the previous one are still accepted (rotation).
"""

import argparse
import base64
import hashlib
import sys
import time
import uuid
from dataclasses import dataclass, field

import jwt
import psycopg
from psycopg_pool import ConnectionPool

from app.config import Settings, get_settings
from app.db import borrow, connect, tenant_scope
from app.domain import User

ALGORITHM = "RS256"
CLOCK_SLACK_S = 60  # tolerated difference between servers' clocks


class AuthError(Exception):
    """The request can't be tied to a user: no, bad, or expired token, or an unknown user."""


@dataclass(frozen=True)
class Claims:
    user_id: str
    tenant_id: str


def key_id(public_pem: bytes) -> str:
    """A short, stable name for a public key: the first 16 hex digits of its SHA-256."""
    return hashlib.sha256(public_pem.strip()).hexdigest()[:16]


@dataclass(frozen=True)
class TokenKeys:
    """The key that signs new tokens, and every public key accepted when checking one."""

    private_pem: bytes | None  # None where tokens are only checked
    public_pems: dict[str, bytes] = field(default_factory=dict)  # kid → public key
    max_ttl_s: int = 900  # the longest lifetime accepted, whatever a token claims

    @property
    def signing_kid(self) -> str:
        if not self.public_pems:
            raise ValueError("no public key")
        return next(iter(self.public_pems))  # the current key comes first

    @classmethod
    def from_pems(
        cls, private_pem: bytes | None, *public_pems: bytes, max_ttl_s: int = 900
    ) -> "TokenKeys":
        pems = {key_id(pem): pem.strip() for pem in public_pems if pem}
        return cls(private_pem, pems, max_ttl_s)

    @classmethod
    def from_settings(cls, settings: Settings) -> "TokenKeys":
        """Keys from .env (base64 of each PEM file, so each fits on one line)."""
        if not settings.jwt_public_key:
            raise ValueError("JWT_PUBLIC_KEY is not set (run python3 scripts/make_env.py)")
        decode = base64.b64decode
        private = decode(settings.jwt_private_key) if settings.jwt_private_key else None
        previous = (
            decode(settings.jwt_previous_public_key) if settings.jwt_previous_public_key else b""
        )
        return cls.from_pems(
            private, decode(settings.jwt_public_key), previous, max_ttl_s=settings.token_ttl_s
        )


def issue_token(
    user_id: str, tenant_id: str, *, keys: TokenKeys, ttl_s: int = 900, now: float | None = None
) -> str:
    if not keys.private_pem:
        raise ValueError("JWT_PRIVATE_KEY is not set (run python3 scripts/make_env.py)")
    issued = int(now if now is not None else time.time())
    claims = {"sub": str(user_id), "tenant": str(tenant_id), "iat": issued, "exp": issued + ttl_s}
    return jwt.encode(
        claims, keys.private_pem, algorithm=ALGORITHM, headers={"kid": keys.signing_kid}
    )


def verify_token(token: str, *, keys: TokenKeys) -> Claims:
    """Check the key id, the signature, the expiry, and that both ids are well formed."""
    try:
        public = keys.public_pems.get(jwt.get_unverified_header(token).get("kid", ""))
        if public is None:
            raise AuthError("unknown key")
        # algorithms=[RS256] pins the algorithm: an HS256 token (even one "signed" with the
        # public key as a shared secret) or an unsigned "alg: none" token is refused.
        payload = jwt.decode(
            token,
            public,
            algorithms=[ALGORITHM],
            options={"require": ["sub", "tenant", "iat", "exp"]},
        )
        if payload["exp"] - payload["iat"] > keys.max_ttl_s + CLOCK_SLACK_S:
            raise AuthError("lifetime too long")  # 15 minutes is enforced here too (T-6)
        return Claims(
            user_id=str(uuid.UUID(payload["sub"])), tenant_id=str(uuid.UUID(payload["tenant"]))
        )
    except AuthError:
        raise
    except (jwt.PyJWTError, ValueError, TypeError) as error:
        raise AuthError(type(error).__name__) from None


def authenticate(token: str, *, keys: TokenKeys, db: psycopg.Connection | ConnectionPool) -> User:
    """The user a token names, with their current roles and permissions."""
    claims = verify_token(token, keys=keys)
    with borrow(db) as conn, tenant_scope(conn, claims.tenant_id):
        row = conn.execute(
            "SELECT id, tenant_id, email, roles, permissions FROM users WHERE id = %s",
            (claims.user_id,),
        ).fetchone()
    if row is None:  # deleted, or not in that tenant (RLS hides it)
        raise AuthError("unknown user")
    user_id, tenant_id, email, roles, permissions = row
    return User(
        id=str(user_id), tenant_id=str(tenant_id), email=email, roles=roles, permissions=permissions
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.auth", description="Issue a dev token.")
    sub = parser.add_subparsers(dest="command", required=True)
    token = sub.add_parser("token", help="print an access token for a seeded user")
    token.add_argument("--tenant", required=True)
    token.add_argument("--email", required=True)
    args = parser.parse_args(argv)

    try:
        print(token_for(get_settings(), args.tenant, args.email))
    except LookupError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


def token_for(settings: Settings, tenant_name: str, email: str) -> str:
    """A dev token for a seeded user (CLI, demo seed); LookupError if there is no such user."""
    with connect(settings.database_url, autocommit=True) as conn:
        tenant = conn.execute("SELECT id FROM tenants WHERE name = %s", (tenant_name,)).fetchone()
        if tenant is None:
            raise LookupError(f"no tenant {tenant_name!r}")
        with tenant_scope(conn, tenant[0]):
            user = conn.execute("SELECT id FROM users WHERE email = %s", (email,)).fetchone()
    if user is None:
        raise LookupError(f"no user {email!r} in {tenant_name!r}")
    keys = TokenKeys.from_settings(settings)
    return issue_token(user[0], tenant[0], keys=keys, ttl_s=settings.token_ttl_s)


if __name__ == "__main__":
    sys.exit(main())
