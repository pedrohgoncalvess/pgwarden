# syntax=docker/dockerfile:1.7
FROM python:3.13-slim AS base

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PATH="/app/.venv/bin:$PATH"

FROM base AS dependencies

COPY --from=ghcr.io/astral-sh/uv:0.11.16 /uv /bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

COPY pyproject.toml uv.lock ./
COPY analytics/pyproject.toml analytics/pyproject.toml
COPY notifier/pyproject.toml notifier/pyproject.toml
# uv's cache supports concurrent access across service builds.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace --package analytics

FROM base AS runtime

COPY --from=dependencies /app/.venv /app/.venv

COPY analytics ./analytics

CMD ["python", "-m", "analytics.main"]
