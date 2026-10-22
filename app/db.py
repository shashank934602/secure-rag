"""Database connections. The app connects as `rag_app` (DATABASE_URL), never as the admin."""

import psycopg
from pgvector.psycopg import register_vector


def connect(url: str) -> psycopg.Connection:
    """Open a connection that sends and receives `vector` columns as lists of numbers."""
    conn = psycopg.connect(url)
    register_vector(conn)
    return conn
