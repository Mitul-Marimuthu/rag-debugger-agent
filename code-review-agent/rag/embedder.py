from typing import Optional

from openai import OpenAI
from config import settings


_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


def get_embeddings(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    client = _get_client()
    cleaned = [t[:8191] for t in texts]

    response = client.embeddings.create(
        model=settings.embedding_model,
        input=cleaned,
    )

    return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]


def get_embedding(text: str) -> list[float]:
    return get_embeddings([text])[0]
