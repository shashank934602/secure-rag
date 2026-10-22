"""Alembic entry point: run migrations as the admin (DATABASE_ADMIN_URL), one transaction each."""

from alembic import context
from dotenv import load_dotenv
from psycopg.conninfo import conninfo_to_dict
from sqlalchemy import create_engine

from app.config import ROOT, Settings

# Read fresh settings (not the cached get_settings()), so tests can point at their own database.
load_dotenv(ROOT / ".env", override=False)
settings = Settings()
if not settings.database_admin_url or not settings.database_url:
    raise RuntimeError("Set DATABASE_ADMIN_URL and DATABASE_URL (see .env.example).")

# The first migration creates the rag_app role with the password from DATABASE_URL.
context.config.attributes["rag_app_password"] = conninfo_to_dict(settings.database_url)["password"]


def run_migrations_online() -> None:
    url = settings.database_admin_url.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, transaction_per_migration=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Offline (SQL script) mode is not used in this project.")
run_migrations_online()
