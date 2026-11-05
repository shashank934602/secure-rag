"""Settings from the environment and `.env`. Models, sizes, and limits live here, never inline."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    # Models: "provider:model" strings, passed to init_chat_model / the embeddings factory.
    chat_model: str = "groq:openai/gpt-oss-120b"
    chat_temperature: float = 0.0
    chat_timeout_s: float = 30.0  # a network failure must not hang a request (tester T-4)
    embedding_model: str = "mistralai:mistral-embed"  # 1024 numbers per text (ADR-0005)

    # Corpus and chunking (spec 01 D1, D13).
    corpus_dir: Path = ROOT / "data" / "sample"
    chunk_size: int = 400
    chunk_overlap: int = 50
    # Chunk sizes are measured with this tokenizer. Mistral counts tokens slightly differently,
    # but 400 is far below mistral-embed's 8,192-token input limit, so the estimate is safe.
    tokenizer_encoding: str = "cl100k_base"

    # Retrieval (spec 03 D7): dense = vector only; hybrid = vector + keyword, fused with RRF.
    top_k: int = 5
    # Defaults = the best setup in the Phase 3 eval (hybrid + rerank: MRR 1.000 vs 0.917 dense).
    # The in-memory index (no DATABASE_URL) is dense only.
    retrieval_mode: Literal["dense", "keyword", "hybrid"] = "hybrid"
    candidates: int = 20  # per search list before fusion, and the number reranked
    # Reranking (spec 03 D4–D5): a local cross-encoder picks top_k of the candidates; if the
    # best score is below the threshold, the answer is No-Answer without calling the LLM.
    rerank: bool = True
    reranker_model: str = "BAAI/bge-reranker-base"
    # Exact model commits (spec 07 D6): the same name can point at new weights later.
    reranker_revision: str = "2cfc18c9415c912f9d8155881c133215df768a70"
    rerank_threshold: float = 0.0

    # Guards (spec 05). The input guard refuses injection attempts before any search or LLM call.
    input_guard: bool = True
    injection_threshold: float = 0.5
    injection_model: str = "protectai/deberta-v3-base-prompt-injection-v2"
    injection_revision: str = "90c9989b1a342275dd0d1a95aad283c04e075671"
    # Context guard: drop injected chunks (when the classifier is on), mask personal data.
    context_guard: bool = True
    # Grounding judge (spec 05 D6): a different model family from the generator.
    grounding_judge: bool = True
    judge_model: str = "mistralai:ministral-8b-2512"  # dated, not -latest (spec 07 D6)
    judge_timeout_s: float = 15.0
    # The eval judge scores answers for the eval only (spec 07 D6): not the grounding judge, so the
    # guard doesn't grade itself.
    eval_judge_model: str = "mistralai:ministral-14b-2512"

    # Database (spec 02 D1, D3). The app connects as rag_app; migrations run as the admin.
    database_url: str = ""
    database_admin_url: str = ""
    tenant: str = "Aldermoor"  # the CLI, eval, and ingest default; the API uses the token's tenant
    roles: list[str] = ["employee"]  # CLI and eval scope; the API uses the logged-in user's roles

    # Access tokens (spec 04 D5): HS256-signed JWTs; the secret lives only in .env.
    jwt_secret: str = ""
    token_ttl_s: int = 3600

    # Audit trail (spec 06 D4): key for the HMAC of each question; the raw text is never stored.
    audit_hmac_key: str = ""

    # Abuse and cost limits (spec 09 D2–D4). Without REDIS_URL the counters live in this process.
    redis_url: str = ""
    rate_limit_user_per_min: int = 20
    rate_limit_tenant_per_min: int = 120
    tenant_daily_token_budget: int = 200_000  # model tokens per tenant per UTC day


@lru_cache
def get_settings() -> Settings:
    # Model clients read API keys from the process environment, not from Settings,
    # so export .env there too. Real environment variables win over .env.
    load_dotenv(ROOT / ".env", override=False)
    return Settings()
