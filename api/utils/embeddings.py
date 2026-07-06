"""Embedding provider utilities.

Embeddings are generated using the bgem3 model with a fixed dimension of 1024.
The provider is enabled when ``OPENAI_API_KEY`` is present and is expected to
expose an OpenAI-compatible ``/embeddings`` endpoint. If no key is configured,
``generate_embedding`` returns ``None`` and callers store a NULL value. This
keeps local development and unit tests working without external credentials.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from utils.env_var import get_env_var

if TYPE_CHECKING:
    from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

EMBEDDING_DIMENSION = 1024
EMBEDDING_MODEL = "bgem3"

_openai_client: AsyncOpenAI | None = None


def _get_openai_client() -> AsyncOpenAI | None:
    global _openai_client
    api_key = get_env_var("OPENAI_API_KEY")
    if not api_key:
        return None
    if _openai_client is None:
        from openai import AsyncOpenAI

        _openai_client = AsyncOpenAI(api_key=api_key)
    return _openai_client


async def generate_embedding(text: str) -> list[float] | None:
    """Generate a dense embedding for ``text`` using the fixed bgem3 model.

    Returns ``None`` when the text is empty or no provider is configured.
    """
    if not text or not text.strip():
        return None

    client = _get_openai_client()
    if not client:
        logger.debug("No embedding provider configured; skipping embedding generation.")
        return None

    try:
        response = await client.embeddings.create(
            input=text,
            model=EMBEDDING_MODEL,
        )
        return response.data[0].embedding
    except Exception as exc:
        logger.warning("Embedding generation failed: %s", exc)
        return None
