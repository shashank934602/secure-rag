"""Settings from the environment and `.env`. Models, sizes, and limits live here, never inline."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    # Models: "provider:model" strings, passed to init_chat_model / the embeddings factory.
    chat_model: str = "groq:openai/gpt-oss-120b"
    chat_temperature: float = 0.0
    embedding_model: str = "openai:text-embedding-3-small"

    # Corpus and chunking (spec 01 D1, D13).
    corpus_dir: Path = ROOT / "data" / "sample"
    chunk_size: int = 400
    chunk_overlap: int = 50
    tokenizer_encoding: str = "cl100k_base"  # the tokenizer of text-embedding-3-small

    # Retrieval.
    top_k: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
