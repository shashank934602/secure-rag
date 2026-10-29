"""Database connections. The app connects as `rag_app` (DATABASE_URL), never as the admin."""

import psycopg
from pgvector.psycopg import register_vector
from psycopg_pool import ConnectionPool


def connect(url: str, *, autocommit: bool = False, name: str = "rag-app") -> psycopg.Connection:
    """Open a connection that sends and receives `vector` columns as lists of numbers.

    With `autocommit=True`, each `with conn.transaction():` block is its own transaction.
    """
    conn = psycopg.connect(url, autocommit=autocommit, application_name=name)
    register_vector(conn)
    return conn


def make_pool(url: str, *, name: str = "rag-app", max_size: int = 5) -> ConnectionPool:
    """A small pool of autocommit connections for a long-running app (the API).

    Each connection is checked before it is handed out, so after a database restart the next
    request gets a fresh connection instead of a dead one; concurrent requests don't share one.
    """
    return ConnectionPool(
        url,
        min_size=1,
        max_size=max_size,
        open=True,
        kwargs={"autocommit": True, "application_name": name},
        configure=register_vector,
        check=ConnectionPool.check_connection,
    )
