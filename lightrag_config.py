"""
Shared LightRAG initialisation — import this in other scripts.
"""

import os
import asyncio
import numpy as np
import anthropic
import voyageai
from lightrag import LightRAG, QueryParam
from lightrag.utils import EmbeddingFunc

ANTHROPIC_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
VOYAGE_KEY     = os.getenv("VOYAGE_API_KEY", "")
LIGHTRAG_DIR   = os.getenv("LIGHTRAG_DIR", "/lightrag-db")

_anthropic = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
_voyage    = voyageai.Client(api_key=VOYAGE_KEY)

EMBEDDING_DIM = 1024  # voyage-4-lite output dimension


async def llm_func(prompt, system_prompt=None, **kwargs):
    response = _anthropic.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=system_prompt or "You are a helpful scientific assistant.",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


async def embedding_func(texts: list[str]) -> np.ndarray:
    result = _voyage.embed(texts, model="voyage-4-lite")
    return np.array(result.embeddings)


def get_rag() -> LightRAG:
    os.makedirs(LIGHTRAG_DIR, exist_ok=True)
    return LightRAG(
        working_dir=LIGHTRAG_DIR,
        llm_model_func=llm_func,
        embedding_func=EmbeddingFunc(
            embedding_dim=EMBEDDING_DIM,
            max_token_size=8192,
            func=embedding_func,
        ),
    )
