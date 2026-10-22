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
