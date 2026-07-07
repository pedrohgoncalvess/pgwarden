"""
Embedding provider utilities.

This module uses BGE-M3 embeddings (1024 dims). The generation priority is:

1. OpenRouter (https://openrouter.ai/api/v1/embeddings) when OPENROUTER_API_KEY
   is present. This avoids downloading any local model.
2. Local sentence-transformers model ``BAAI/bge-m3`` when no OpenRouter key is
   configured.

There is no other provider switching; the model and dimension are hardcoded.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from utils.env_var import get_env_var

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "BAAI/bge-m3"
EMBEDDING_DIMENSION = 1024

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/embeddings"
OPENROUTER_EMBEDDING_MODEL = "baai/bge-m3"

_sentence_transformer_model: object | None = None


def _get_openrouter_api_key() -> str | None:
    return get_env_var("OPENROUTER_API_KEY")


def _get_sentence_transformer_model() -> object:
    global _sentence_transformer_model
    if _sentence_transformer_model is None:
        from sentence_transformers import SentenceTransformer

        logger.info("Loading sentence-transformers model: %s", EMBEDDING_MODEL)
        _sentence_transformer_model = SentenceTransformer(EMBEDDING_MODEL)
    return _sentence_transformer_model


async def _generate_openrouter_embedding(text: str, api_key: str) -> list[float] | None:
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(
                OPENROUTER_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": OPENROUTER_EMBEDDING_MODEL,
                    "input": text,
                    "encoding_format": "float",
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]
        except Exception as exc:
            logger.warning("OpenRouter embedding generation failed: %s", exc)
            return None


async def _generate_local_embedding(text: str) -> list[float] | None:
    model = _get_sentence_transformer_model()
    try:
        embedding = await asyncio.to_thread(
            model.encode,
            text,
            normalize_embeddings=True,
        )
        return embedding.tolist()
    except Exception as exc:
        logger.warning("Local embedding generation failed: %s", exc)
        return None


async def generate_embedding(text: str) -> list[float] | None:
    """Generate a dense embedding for ``text`` using BGE-M3.

    OpenRouter is used when ``OPENROUTER_API_KEY`` is set; otherwise the local
    sentence-transformers model is loaded and used.

    Returns ``None`` when the text is empty or the configured generator fails.
    """
    if not text or not text.strip():
        return None

    api_key = _get_openrouter_api_key()
    if api_key:
        return await _generate_openrouter_embedding(text, api_key)

    return await _generate_local_embedding(text)
