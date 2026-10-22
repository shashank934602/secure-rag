"""Settings from the environment and `.env`. Models, sizes, and limits live here, never inline."""

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    # Models: "provider:model" strings, passed to init_chat_model / the embeddings factory.
    chat_model: str = "groq:openai/gpt-oss-120b"
    chat_temperature: float = 0.0
    embedding_model: str = "mistralai:mistral-embed"  # 1024 numbers per text (ADR-0005)

    # Corpus and chunking (spec 01 D1, D13).
    corpus_dir: Path = ROOT / "data" / "sample"
    chunk_size: int = 400
    chunk_overlap: int = 50
    # Chunk sizes are measured with this tokenizer. Mistral counts tokens slightly differently,
    # but 400 is far below mistral-embed's 8,192-token input limit, so the estimate is safe.
    tokenizer_encoding: str = "cl100k_base"

    # Retrieval.
    top_k: int = 5

    # Database (spec 02 D1, D3). The app connects as rag_app; migrations run as the admin.
    database_url: str = ""
    database_admin_url: str = ""
    tenant: str = "Aldermoor"  # the one seeded tenant until auth arrives (Phase 4)


@lru_cache
def get_settings() -> Settings:
    # Model clients read API keys from the process environment, not from Settings,
    # so export .env there too. Real environment variables win over .env.
    load_dotenv(ROOT / ".env", override=False)
    return Settings()
