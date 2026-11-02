"""S2 (ISS-036): a token is turned into a user whose roles are read from the database.

Needs Docker:   uv run pytest -m db
"""

import psycopg
import pytest

from app.auth import AuthError, authenticate, issue_token
from app.db import connect
from tests.conftest import PgUrls

pytestmark = pytest.mark.db
SECRET = "test-secret-0123456789abcdef0123456789abcdef"


def _ids(pg: PgUrls, email: str) -> tuple[str, str]:
    with psycopg.connect(pg.admin) as admin:
        user_id, tenant_id = admin.execute(
            "SELECT id, tenant_id FROM users WHERE email = %s", (email,)
        ).fetchone()
    return str(user_id), str(tenant_id)


def test_a_valid_token_becomes_the_user_with_roles_from_the_database(pg: PgUrls) -> None:
    user_id, tenant_id = _ids(pg, "harriet@aldermoor.example.com")
    with connect(pg.app, autocommit=True) as conn:
        user = authenticate(issue_token(user_id, tenant_id, secret=SECRET), secret=SECRET, db=conn)

    assert (user.email, user.roles, user.permissions) == (
        "harriet@aldermoor.example.com",
        ["employee", "hr"],
        ["uploader", "pii:read"],  # pii:read added in migration 0004
    )
    assert user.scope.tenant_id == tenant_id and user.scope.roles == ["employee", "hr"]


def test_a_role_removed_in_the_database_is_gone_on_the_next_request(pg: PgUrls) -> None:
    user_id, tenant_id = _ids(pg, "harriet@aldermoor.example.com")
    token = issue_token(user_id, tenant_id, secret=SECRET)  # issued while she still had hr
    with psycopg.connect(pg.admin, autocommit=True) as admin:
        admin.execute("UPDATE users SET roles = '{employee}' WHERE id = %s", (user_id,))
    try:
        with connect(pg.app, autocommit=True) as conn:
            assert authenticate(token, secret=SECRET, db=conn).roles == ["employee"]
    finally:
        with psycopg.connect(pg.admin, autocommit=True) as admin:
            admin.execute("UPDATE users SET roles = '{employee,hr}' WHERE id = %s", (user_id,))


def test_a_user_claimed_under_another_tenant_is_not_found(pg: PgUrls) -> None:
    # Even a correctly signed token can't reach a user of another tenant: RLS hides the row.
    alice_id, _ = _ids(pg, "alice@aldermoor.example.com")
    _, northgate_id = _ids(pg, "ned@northgate.example.com")
    with connect(pg.app, autocommit=True) as conn, pytest.raises(AuthError):
        authenticate(issue_token(alice_id, northgate_id, secret=SECRET), secret=SECRET, db=conn)


def test_a_deleted_user_is_rejected(pg: PgUrls) -> None:
    _, tenant_id = _ids(pg, "alice@aldermoor.example.com")
    ghost = "00000000-0000-0000-0000-000000000000"
    with connect(pg.app, autocommit=True) as conn, pytest.raises(AuthError):
        authenticate(issue_token(ghost, tenant_id, secret=SECRET), secret=SECRET, db=conn)
