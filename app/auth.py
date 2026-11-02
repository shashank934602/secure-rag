"""Authentication (spec 04 D5): a signed token says who you are; the database says what you may see.

    uv run python -m app.auth token --tenant Aldermoor --email alice@aldermoor.example.com

The token holds only the user id (`sub`), the tenant id, and an expiry. Roles and permissions are
loaded from the database on every request, inside that tenant's scope, so a removed role takes
effect at once and a token can never reach a user of another tenant (row-level security).
"""

import argparse
import sys
import time
import uuid
from dataclasses import dataclass

import jwt
import psycopg
from psycopg_pool import ConnectionPool

from app.config import get_settings
from app.db import borrow, connect, tenant_scope
from app.domain import User

ALGORITHM = "HS256"


class AuthError(Exception):
    """The request can't be tied to a user: no, bad, or expired token, or an unknown user."""


@dataclass(frozen=True)
class Claims:
    user_id: str
    tenant_id: str


def issue_token(
    user_id: str, tenant_id: str, *, secret: str, ttl_s: int = 3600, now: float | None = None
) -> str:
    if not secret:
        raise ValueError("JWT_SECRET is not set (see .env.example)")
    issued = int(now if now is not None else time.time())
    claims = {"sub": str(user_id), "tenant": str(tenant_id), "iat": issued, "exp": issued + ttl_s}
    return jwt.encode(claims, secret, algorithm=ALGORITHM)


def verify_token(token: str, *, secret: str) -> Claims:
    """Check the signature, the expiry, and that both ids are present and well formed."""
    try:
        # algorithms=[...] pins HS256, so an unsigned "alg: none" token is refused.
        payload = jwt.decode(
            token, secret, algorithms=[ALGORITHM], options={"require": ["sub", "tenant", "exp"]}
        )
        return Claims(
            user_id=str(uuid.UUID(payload["sub"])), tenant_id=str(uuid.UUID(payload["tenant"]))
        )
    except (jwt.PyJWTError, ValueError, TypeError) as error:
        raise AuthError(type(error).__name__) from None


def authenticate(token: str, *, secret: str, db: psycopg.Connection | ConnectionPool) -> User:
    """The user a token names, with their current roles and permissions."""
    claims = verify_token(token, secret=secret)
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

    settings = get_settings()
    with connect(settings.database_url, autocommit=True) as conn:
        tenant = conn.execute("SELECT id FROM tenants WHERE name = %s", (args.tenant,)).fetchone()
        if tenant is None:
            print(f"Error: no tenant {args.tenant!r}", file=sys.stderr)
            return 1
        with tenant_scope(conn, tenant[0]):
            user = conn.execute("SELECT id FROM users WHERE email = %s", (args.email,)).fetchone()
    if user is None:
        print(f"Error: no user {args.email!r} in {args.tenant!r}", file=sys.stderr)
        return 1
    print(issue_token(user[0], tenant[0], secret=settings.jwt_secret, ttl_s=settings.token_ttl_s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
