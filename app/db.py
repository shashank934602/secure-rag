"""Database connections. The app connects as `rag_app` (DATABASE_URL), never as the admin."""

import psycopg
from pgvector.psycopg import register_vector


def connect(url: str, *, autocommit: bool = False) -> psycopg.Connection:
    """Open a connection that sends and receives `vector` columns as lists of numbers.

    With `autocommit=True`, each `with conn.transaction():` block is its own transaction.
    """
    conn = psycopg.connect(url, autocommit=autocommit)
    register_vector(conn)
    return conn
