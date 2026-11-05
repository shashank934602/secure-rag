"""scripts/make_env.py (spec 08 D4, ISS-065): .env is completed, never overwritten."""

from urllib.parse import urlsplit

from scripts.make_env import complete, parse, rsa_key_pair


def _fake_keys() -> tuple[str, str]:
    return "cHJpdmF0ZQ==", "cHVibGlj"


EXAMPLE = """# comment
GROQ_API_KEY=
MISTRAL_API_KEY=
POSTGRES_PASSWORD=
DATABASE_ADMIN_URL=postgresql://postgres:<POSTGRES_PASSWORD>@127.0.0.1:5433/rag
DATABASE_URL=postgresql://rag_app:<app password>@127.0.0.1:5433/rag
RAG_APP_PASSWORD=
JWT_PRIVATE_KEY=
JWT_PUBLIC_KEY=
AUDIT_HMAC_KEY=""".splitlines()


def test_a_fresh_env_gets_every_local_secret_and_matching_urls() -> None:
    out, filled = complete(EXAMPLE, _fake_keys)
    values = parse(out)

    assert set(filled) >= {
        "POSTGRES_PASSWORD",
        "RAG_APP_PASSWORD",
        "AUDIT_HMAC_KEY",
        "JWT_PRIVATE_KEY",
        "JWT_PUBLIC_KEY",
    }
    assert urlsplit(values["DATABASE_URL"]).password == values["RAG_APP_PASSWORD"]
    assert urlsplit(values["DATABASE_ADMIN_URL"]).password == values["POSTGRES_PASSWORD"]
    assert len(values["AUDIT_HMAC_KEY"]) == 64  # 32 random bytes, hex
    assert values["JWT_PUBLIC_KEY"] == "cHVibGlj"
    assert values["GROQ_API_KEY"] == ""  # the person's own keys are left for them
    assert out[0] == "# comment"  # comments and order are kept


def test_existing_values_are_never_overwritten() -> None:
    once, _ = complete(EXAMPLE, _fake_keys)
    twice, filled = complete(once, _fake_keys)
    assert twice == once and filled == []


def test_an_older_env_keeps_its_app_password() -> None:
    older = ["DATABASE_URL=postgresql://rag_app:kept-pw@127.0.0.1:5433/rag", "AUDIT_HMAC_KEY=j"]
    out, filled = complete(older, _fake_keys)
    values = parse(out)
    assert values["RAG_APP_PASSWORD"] == "kept-pw"
    assert out[0] == older[0] and values["AUDIT_HMAC_KEY"] == "j"  # untouched
    assert "RAG_APP_PASSWORD" in filled and "AUDIT_HMAC_KEY" not in filled
    assert "JWT_PUBLIC_KEY" in filled  # an older .env gets the RS256 pair added


def test_the_generated_key_pair_signs_and_verifies_tokens() -> None:
    import base64

    from app.auth import TokenKeys, issue_token, verify_token

    private, public = rsa_key_pair()
    keys = TokenKeys.from_pems(base64.b64decode(private), base64.b64decode(public))
    claims = verify_token(
        issue_token(
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
            keys=keys,
        ),
        keys=keys,
    )
    assert claims.tenant_id.endswith("2")
