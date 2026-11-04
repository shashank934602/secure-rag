"""scripts/make_env.py (spec 08 D4, ISS-065): .env is completed, never overwritten."""

from urllib.parse import urlsplit

from scripts.make_env import complete, parse

EXAMPLE = """# comment
GROQ_API_KEY=
MISTRAL_API_KEY=
POSTGRES_PASSWORD=
DATABASE_ADMIN_URL=postgresql://postgres:<POSTGRES_PASSWORD>@127.0.0.1:5433/rag
DATABASE_URL=postgresql://rag_app:<app password>@127.0.0.1:5433/rag
RAG_APP_PASSWORD=
JWT_SECRET=
AUDIT_HMAC_KEY=""".splitlines()


def test_a_fresh_env_gets_every_local_secret_and_matching_urls() -> None:
    out, filled = complete(EXAMPLE)
    values = parse(out)

    assert set(filled) >= {"POSTGRES_PASSWORD", "RAG_APP_PASSWORD", "JWT_SECRET", "AUDIT_HMAC_KEY"}
    assert urlsplit(values["DATABASE_URL"]).password == values["RAG_APP_PASSWORD"]
    assert urlsplit(values["DATABASE_ADMIN_URL"]).password == values["POSTGRES_PASSWORD"]
    assert len(values["JWT_SECRET"]) == 64  # 32 random bytes, hex
    assert values["GROQ_API_KEY"] == ""  # the person's own keys are left for them
    assert out[0] == "# comment"  # comments and order are kept


def test_existing_values_are_never_overwritten() -> None:
    once, _ = complete(EXAMPLE)
    twice, filled = complete(once)
    assert twice == once and filled == []


def test_an_older_env_keeps_its_app_password() -> None:
    older = ["DATABASE_URL=postgresql://rag_app:kept-pw@127.0.0.1:5433/rag", "JWT_SECRET=j"]
    out, filled = complete(older)
    values = parse(out)
    assert values["RAG_APP_PASSWORD"] == "kept-pw"
    assert out[0] == older[0] and values["JWT_SECRET"] == "j"  # untouched
    assert "RAG_APP_PASSWORD" in filled and "JWT_SECRET" not in filled
