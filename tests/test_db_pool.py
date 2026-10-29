"""ISS-028: when the database can't be reached, starting the app fails fast with a clear message."""

import pytest

from app.db import make_pool


def test_an_unreachable_database_fails_fast_with_a_clear_message() -> None:
    url = "postgresql://rag_app:hunter2-secret@127.0.0.1:1/rag"  # nothing listens on port 1

    with pytest.raises(RuntimeError) as error:
        make_pool(url, wait_timeout=1)

    message = str(error.value)
    assert "127.0.0.1:1" in message
    assert "docker compose up -d" in message
    assert "hunter2-secret" not in message  # never print the password
