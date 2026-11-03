"""S1 (ISS-050): the audit log in Postgres — append-only, chained per tenant, tamper-evident.

Needs Docker:   uv run pytest -m db
"""

import threading

import psycopg
import pytest

from app.audit.log import append_events, verify
from app.db import connect
from tests.conftest import PgUrls

pytestmark = pytest.mark.db


def _tenant(pg: PgUrls, name: str) -> str:
    with psycopg.connect(pg.admin) as admin:
        return str(admin.execute("SELECT id FROM tenants WHERE name = %s", (name,)).fetchone()[0])


def _events(n: int, stage: str = "input_guard") -> list[dict]:
    return [
        {"stage": stage, "decision": "ALLOW", "score": 0.01 * i, "details": {"reason": f"r{i}"}}
        for i in range(n)
    ]


def _as_admin(pg: PgUrls, *sql: str) -> None:
    """Simulate an insider with superuser rights: switch the append-only rule off, change data."""
    with psycopg.connect(pg.admin, autocommit=True) as admin:
        admin.execute("ALTER TABLE audit_events DISABLE TRIGGER audit_events_no_change")
        try:
            for statement in sql:
                admin.execute(statement)
        finally:
            admin.execute("ALTER TABLE audit_events ENABLE TRIGGER audit_events_no_change")


def test_events_are_numbered_and_the_chain_verifies(pg: PgUrls) -> None:
    aldermoor = _tenant(pg, "Aldermoor")
    with connect(pg.app, autocommit=True) as conn:
        assert append_events(conn, aldermoor, _events(3)) == [1, 2, 3]
        assert append_events(conn, aldermoor, _events(2)) == [4, 5]
        result = verify(conn, aldermoor)
    assert (result.ok, result.rows_checked) == (True, 5)


def test_the_app_cannot_change_or_delete_audit_events(pg: PgUrls) -> None:
    aldermoor = _tenant(pg, "Aldermoor")
    with connect(pg.app, autocommit=True) as conn:
        append_events(conn, aldermoor, _events(1))
        for sql in ("UPDATE audit_events SET decision = 'BLOCK'", "DELETE FROM audit_events"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE audit_events SET decision = 'BLOCK'",
        "DELETE FROM audit_events",
        "TRUNCATE audit_events",
    ],
)
def test_even_the_admin_is_stopped_by_the_append_only_rule(pg: PgUrls, sql: str) -> None:
    aldermoor = _tenant(pg, "Aldermoor")
    with connect(pg.app, autocommit=True) as conn:
        append_events(conn, aldermoor, _events(1))
    with psycopg.connect(pg.admin, autocommit=True) as admin:
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            admin.execute(sql)


def test_an_edit_behind_the_rules_back_is_detected_by_verify(pg: PgUrls) -> None:
    aldermoor = _tenant(pg, "Aldermoor")
    with connect(pg.app, autocommit=True) as conn:
        append_events(conn, aldermoor, _events(5))
    _as_admin(
        pg,
        f"UPDATE audit_events SET decision = 'BLOCK' WHERE tenant_id = '{aldermoor}' AND seq = 3",
    )

    with connect(pg.app, autocommit=True) as conn:
        result = verify(conn, aldermoor)
    assert (result.ok, result.first_broken) == (False, 3)


def test_a_deletion_behind_the_rules_back_is_detected_by_verify(pg: PgUrls) -> None:
    aldermoor = _tenant(pg, "Aldermoor")
    with connect(pg.app, autocommit=True) as conn:
        append_events(conn, aldermoor, _events(5))
    _as_admin(pg, f"DELETE FROM audit_events WHERE tenant_id = '{aldermoor}' AND seq = 2")

    with connect(pg.app, autocommit=True) as conn:
        result = verify(conn, aldermoor)
    assert (result.ok, result.first_broken) == (False, 3)
    assert "gap" in result.reason


def test_each_tenant_has_its_own_chain_and_cannot_see_the_other(pg: PgUrls) -> None:
    aldermoor, northgate = _tenant(pg, "Aldermoor"), _tenant(pg, "Northgate Haulage")
    with connect(pg.app, autocommit=True) as conn:
        append_events(conn, aldermoor, _events(3))
        assert append_events(conn, northgate, _events(2)) == [1, 2]  # its own numbering
        assert verify(conn, northgate).rows_checked == 2  # RLS: Aldermoor's rows invisible


def test_concurrent_appends_never_fork_the_chain(pg: PgUrls) -> None:
    aldermoor = _tenant(pg, "Aldermoor")

    def writer() -> None:
        with connect(pg.app, autocommit=True) as conn:
            for _ in range(10):
                append_events(conn, aldermoor, _events(1))

    threads = [threading.Thread(target=writer) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    with connect(pg.app, autocommit=True) as conn:
        result = verify(conn, aldermoor)
    assert (result.ok, result.rows_checked) == (True, 40)
