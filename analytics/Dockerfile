# syntax=docker/dockerfile:1.7
FROM python:3.13-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock ./
COPY analytics/pyproject.toml analytics/pyproject.toml
COPY notifier/pyproject.toml notifier/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    uv sync --frozen --no-dev --package analytics

COPY analytics ./analytics

CMD ["python", "-m", "analytics.main"]
