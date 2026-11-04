# One image for the `migrate`, `seed`, and `api` services (spec 08 D2, ISS-065).
#   docker compose up            builds it on first use
# No secrets are baked in: they come from .env at run time. The local models (injection
# classifier, reranker) download on first use into the `hf-cache` volume, not into the image.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.6 /uv /bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/home/app/.cache/huggingface

WORKDIR /app

# Dependencies first (cached until the lock file changes); Linux gets the CPU-only PyTorch.
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project

COPY app ./app
COPY db ./db
COPY data ./data
COPY scripts ./scripts

# Run as a normal user, not root.
RUN useradd --create-home --uid 10001 app && mkdir -p "$HF_HOME" && chown -R app /home/app
USER app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
