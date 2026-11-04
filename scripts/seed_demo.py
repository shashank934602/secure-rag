"""Load the demo data for both companies, then print demo tokens (spec 08 D1, ISS-065).

    python -m scripts.seed_demo            # what the `seed` service runs; safe to re-run

Ingest is idempotent (unchanged documents are skipped), so running this again changes nothing.
The tokens are for the fake demo users and expire after TOKEN_TTL_S (default 60 minutes); get a
new one with `docker compose run --rm api python -m app.auth token --tenant … --email …`.
"""

import sys

from app import ingest
from app.auth import token_for
from app.config import get_settings

# (ingest arguments, what it loads)
FOLDERS = [
    ([], "Aldermoor: policies, contracts, org chart (employees)"),
    (["--folder", "data/tenants/aldermoor-finance"], "Aldermoor: payee list (employees)"),
    (
        ["--folder", "data/tenants/aldermoor-hr", "--roles", "hr"],
        "Aldermoor: salary bands (HR only)",
    ),
    (["--tenant", "Northgate Haulage", "--folder", "data/tenants/northgate"], "Northgate Haulage"),
]

# (tenant, email, what they can do)
DEMO_USERS = [
    ("Aldermoor", "alice@aldermoor.example.com", "employee"),
    ("Aldermoor", "harriet@aldermoor.example.com", "HR: sees salary bands and personal data"),
    ("Aldermoor", "audrey@aldermoor.example.com", "auditor: /v1/audit/*"),
    ("Northgate Haulage", "ned@northgate.example.com", "employee of the other company"),
]


def main() -> int:
    for args, what in FOLDERS:
        print(f"→ {what}", flush=True)
        if ingest.main(args) != 0:
            return 1
    settings = get_settings()
    print("\nDemo ready. Open the web page, paste a token, ask a question.")
    print(f"Tokens (valid {settings.token_ttl_s // 60} minutes):")
    for tenant, email, role in DEMO_USERS:
        print(f"\n  {email}  ({role})\n  {token_for(settings, tenant, email)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
