"""Database connections. The app connects as `rag_app` (DATABASE_URL), never as the admin."""

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from pgvector.psycopg import register_vector
from psycopg.conninfo import conninfo_to_dict
from psycopg_pool import ConnectionPool, PoolTimeout


def connect(url: str, *, autocommit: bool = False, name: str = "rag-app") -> psycopg.Connection:
    """Open a connection that sends and receives `vector` columns as lists of numbers.

    With `autocommit=True`, each `with conn.transaction():` block is its own transaction.
    """
    conn = psycopg.connect(url, autocommit=autocommit, application_name=name)
    register_vector(conn)
    return conn


def make_pool(
    url: str, *, name: str = "rag-app", max_size: int = 5, wait_timeout: float = 5.0
) -> ConnectionPool:
    """A small pool of autocommit connections for a long-running app (the API).

    Each connection is checked before it is handed out, so after a database restart the next
    request gets a fresh connection instead of a dead one; concurrent requests don't share one.
    If no connection can be made within `wait_timeout` seconds, fail with a clear message
    instead of retrying forever (ISS-028).
    """
    pool = ConnectionPool(
        url,
        min_size=1,
        max_size=max_size,
        open=True,
        kwargs={"autocommit": True, "application_name": name},
        configure=register_vector,
        check=ConnectionPool.check_connection,
    )
    try:
        pool.wait(timeout=wait_timeout)
    except PoolTimeout:
        pool.close()
        raise RuntimeError(
            f"Cannot reach the database at {_address(url)}. Is Docker running? "
            "Start Docker Desktop, then run: docker compose up -d"
        ) from None
    return pool


def _address(url: str) -> str:
    """host:port from a connection URL, without the user or password."""
    info = conninfo_to_dict(url)
    return f"{info.get('host', 'localhost')}:{info.get('port', 5432)}"


@contextmanager
def tenant_scope(conn: psycopg.Connection, tenant_id: object) -> Iterator[psycopg.Connection]:
    """One transaction that runs as `tenant_id`: row-level security then hides every other
    tenant's documents, chunks, and users, even from a query that forgets `WHERE tenant_id`.

    SET LOCAL (`set_config(..., true)`) ends with the transaction, so a pooled connection never
    carries one request's tenant into the next.
    """
    with conn.transaction():
        conn.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
        yield conn


@contextmanager
def borrow(db: psycopg.Connection | ConnectionPool) -> Iterator[psycopg.Connection]:
    """Use one connection (tests, CLI) as is, or borrow a checked one from a pool (the API)."""
    if isinstance(db, ConnectionPool):
        with db.connection() as conn:  # checked alive, returned to the pool afterwards
            yield conn
    else:
        yield db
