"""Create or complete `.env` for the demo stack (spec 08 D4, ISS-065). Standard library only.

    python3 scripts/make_env.py          # then paste GROQ_API_KEY and MISTRAL_API_KEY into .env

- Starts from `.env.example` when `.env` doesn't exist.
- Generates every local secret that is empty: the two database passwords, JWT_SECRET,
  AUDIT_HMAC_KEY; fills the database URLs from them.
- Never overwrites a value that is already set, and never prints a secret: only key names.
- RAG_APP_PASSWORD is taken from an existing DATABASE_URL when there is one (older .env files),
  so the app keeps the password its database role already has.
"""

import os
import secrets
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
GENERATED = {
    "POSTGRES_PASSWORD": 16,
    "RAG_APP_PASSWORD": 16,
    "JWT_SECRET": 32,
    "AUDIT_HMAC_KEY": 32,
}
NEEDED_FROM_YOU = ("GROQ_API_KEY", "MISTRAL_API_KEY")


def parse(lines: list[str]) -> dict[str, str]:
    values = {}
    for line in lines:
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def _placeholder(value: str) -> bool:
    return not value or "<" in value


def complete(lines: list[str]) -> tuple[list[str], list[str]]:
    """The completed lines, and the names of the keys that were filled in."""
    values, filled = parse(lines), []

    def set_value(key: str, value: str) -> None:
        values[key] = value
        filled.append(key)

    app_url = values.get("DATABASE_URL", "")
    if _placeholder(values.get("RAG_APP_PASSWORD", "")) and not _placeholder(app_url):
        password = urlsplit(app_url).password  # keep the password the role already has
        if password:
            set_value("RAG_APP_PASSWORD", password)
    for key, size in GENERATED.items():
        if _placeholder(values.get(key, "")):
            set_value(key, secrets.token_hex(size))
    if _placeholder(values.get("DATABASE_ADMIN_URL", "")):
        set_value(
            "DATABASE_ADMIN_URL",
            f"postgresql://postgres:{values['POSTGRES_PASSWORD']}@127.0.0.1:5433/rag",
        )
    if _placeholder(app_url):
        set_value(
            "DATABASE_URL", f"postgresql://rag_app:{values['RAG_APP_PASSWORD']}@127.0.0.1:5433/rag"
        )

    out, written = [], set()
    for line in lines:  # keep the file's order and comments; replace only what was filled
        key = line.partition("=")[0].strip() if "=" in line else ""
        if key in filled and not line.lstrip().startswith("#"):
            out.append(f"{key}={values[key]}")
            written.add(key)
        else:
            out.append(line)
    missing = [key for key in filled if key not in written]
    if missing:
        out += ["", "# Added by scripts/make_env.py"] + [f"{key}={values[key]}" for key in missing]
    return out, filled


def main() -> int:
    env, example = ROOT / ".env", ROOT / ".env.example"
    source = env if env.exists() else example
    lines = source.read_text(encoding="utf-8").splitlines()
    out, filled = complete(lines)
    if filled or not env.exists():
        tmp = env.with_name(".env.tmp")
        tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
        os.chmod(tmp, 0o600)  # only you can read it
        tmp.replace(env)
    print(f"{'Created' if source is example else 'Checked'} .env")
    print(f"  generated: {', '.join(filled) if filled else 'nothing (all set already)'}")
    empty = [key for key in NEEDED_FROM_YOU if not parse(out).get(key)]
    if empty:
        print(f"  still empty, paste yours into .env: {', '.join(empty)}")
        print(
            "    Groq: https://console.groq.com/keys   Mistral: https://console.mistral.ai/api-keys"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
