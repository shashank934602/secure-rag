"""Shared fixtures. Tests marked `db` get a throwaway Postgres with pgvector, migrated to head."""

from collections.abc import Iterator
from dataclasses import dataclass

import pytest

from app.config import ROOT

PG_IMAGE = "pgvector/pgvector:0.8.7-pg16"  # same image as docker-compose.yml
APP_PASSWORD = "test-app-password"


@dataclass(frozen=True)
class PgUrls:
    admin: str  # migrations and test set-up only
    app: str  # what the application uses: the rag_app role


@pytest.fixture(scope="session")
def pg() -> Iterator[PgUrls]:
    """Start one Postgres container for the test session and run every migration on it."""
    from alembic import command
    from alembic.config import Config
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer(PG_IMAGE, username="postgres", password="test-admin", dbname="rag") as c:
        address = f"{c.get_container_host_ip()}:{c.get_exposed_port(5432)}/rag"
        urls = PgUrls(
            admin=f"postgresql://postgres:test-admin@{address}",
            app=f"postgresql://rag_app:{APP_PASSWORD}@{address}",
        )
        with pytest.MonkeyPatch.context() as env:
            env.setenv("DATABASE_ADMIN_URL", urls.admin)
            env.setenv("DATABASE_URL", urls.app)
            command.upgrade(Config(str(ROOT / "db" / "alembic.ini")), "head")
        yield urls


SEEDED_TENANTS = ("Aldermoor", "Northgate Haulage")


@pytest.fixture(autouse=True)
def _clean_database(request: pytest.FixtureRequest) -> Iterator[None]:
    """Before every `db` test, remove documents (all tenants) and test-made tenants, as the admin.

    The admin is a superuser, so row-level security doesn't hide other tenants' rows from it.
    """
    if request.node.get_closest_marker("db") is None:
        yield
        return
    import psycopg

    urls: PgUrls = request.getfixturevalue("pg")
    with psycopg.connect(urls.admin, autocommit=True) as admin:
        admin.execute("DELETE FROM documents")
        admin.execute("DELETE FROM tenants WHERE name <> ALL(%s)", (list(SEEDED_TENANTS),))
    yield


def act_as(conn, tenant: str = "Aldermoor") -> str:
    """Test helper: make this connection run as `tenant` for the rest of its session; return its id.

    The app sets the scope per transaction (`tenant_scope`); tests set it once per connection.
    """
    (tenant_id,) = conn.execute("SELECT id FROM tenants WHERE name = %s", (tenant,)).fetchone()
    conn.execute("SELECT set_config('app.tenant_id', %s, false)", (str(tenant_id),))
    return str(tenant_id)
