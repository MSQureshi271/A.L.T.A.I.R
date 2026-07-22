"""
app/capabilities/documents/embedding.py — Pluggable Embedding Provider abstraction.

Design goals:
  • EmbeddingProvider is an ABC. New providers are added by subclassing and
    registering in get_embedding_provider() — zero changes to callers.
  • The model name and output dimensions are stored PER CHUNK in the DB, so a
    full-corpus re-embedding job can identify which chunks need to be refreshed
    after a model upgrade.
  • Two task types are supported: DOCUMENT (for ingestion) and QUERY (for search).
    Gemini's task-type distinction improves retrieval quality for asymmetric tasks.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from app.config.settings import settings

logger = logging.getLogger(__name__)

_MAX_GEMINI_BATCH = 100   # Gemini embed_content batch limit


class EmbeddingProvider(ABC):
    """Abstract base for all embedding providers."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Canonical identifier stored in the DB per chunk (e.g. 'gemini/gemini-embedding-2')."""

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Output vector dimensionality."""

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a batch of document texts for storage.
        Returns one vector per input text, in the same order.
        Raises RuntimeError on unrecoverable API failure.
        """

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """
        Embed a single query string for retrieval.
        Uses a separate task type from embed_documents for better recall.
        """


# ── Gemini Provider ────────────────────────────────────────────────────────────

class GeminiEmbeddingProvider(EmbeddingProvider):
    """
    Google Gemini embedding provider using google-genai SDK.

    Supports any Gemini embedding model (gemini-embedding-2, text-multilingual-
    embedding-002, etc.) via settings.EMBEDDING_MODEL. Uses RETRIEVAL_DOCUMENT
    and RETRIEVAL_QUERY task types for asymmetric semantic search.
    """

    def __init__(self, model: str, output_dims: int) -> None:
        self._model = model
        self._dims = output_dims

    @property
    def model_name(self) -> str:
        return f"gemini/{self._model}"

    @property
    def dimensions(self) -> int:
        return self._dims

    def _get_client(self):
        from google import genai  # noqa: PLC0415
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not set. Cannot generate embeddings.")
        return genai.Client(api_key=settings.GEMINI_API_KEY)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        from google.genai import types  # noqa: PLC0415
        client = self._get_client()
        results: list[list[float]] = []

        is_v2 = "gemini-embedding-2" in self._model

        for i in range(0, len(texts), _MAX_GEMINI_BATCH):
            batch = texts[i : i + _MAX_GEMINI_BATCH]
            logger.debug("Embedding document batch %d–%d (%d texts)", i, i + len(batch), len(batch))

            if is_v2:
                # Gemini Embedding 2: prompt task instruction + separate Content objects for individual chunk vectors
                formatted_contents = [
                    types.Content(parts=[types.Part.from_text(text=f"title: none | text: {t}")])
                    for t in batch
                ]
                config = types.EmbedContentConfig(output_dimensionality=self._dims)
            else:
                formatted_contents = batch
                config = types.EmbedContentConfig(
                    task_type="RETRIEVAL_DOCUMENT",
                    output_dimensionality=self._dims,
                )

            def _do_embed():
                return client.models.embed_content(
                    model=f"models/{self._model}",
                    contents=formatted_contents,
                    config=config,
                )

            try:
                response = _call_with_backoff(_do_embed)
                for emb in response.embeddings:
                    results.append(list(emb.values))
            except Exception as exc:
                logger.error("Gemini embedding API failed for batch %d: %s", i, exc)
                raise RuntimeError(f"Embedding API error: {exc}") from exc

        return results

    def embed_query(self, text: str) -> list[float]:
        from google.genai import types  # noqa: PLC0415
        client = self._get_client()

        is_v2 = "gemini-embedding-2" in self._model

        if is_v2:
            # Gemini Embedding 2: task instruction prefix in prompt
            formatted_text = f"task: search result | query: {text}"
            config = types.EmbedContentConfig(output_dimensionality=self._dims)
        else:
            formatted_text = text
            config = types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=self._dims,
            )

        def _do_embed_query():
            return client.models.embed_content(
                model=f"models/{self._model}",
                contents=[formatted_text],
                config=config,
            )

        try:
            response = _call_with_backoff(_do_embed_query)
            return list(response.embeddings[0].values)
        except Exception as exc:
            logger.error("Gemini query embedding failed: %s", exc)
            raise RuntimeError(f"Embedding API error: {exc}") from exc


def _call_with_backoff(fn, max_retries: int = 3, initial_delay: float = 1.0):
    """Execute a function with exponential backoff retries on failure."""
    import time  # noqa: PLC0415
    delay = initial_delay
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries:
                logger.warning(
                    "Embedding API call failed (attempt %d/%d): %s. Retrying in %.1fs...",
                    attempt + 1, max_retries + 1, exc, delay
                )
                time.sleep(delay)
                delay *= 2.0
            else:
                logger.error("Embedding API call failed after %d attempts: %s", max_retries + 1, exc)
    raise RuntimeError(f"Embedding API error after retries: {last_exc}") from last_exc


# ── Factory ────────────────────────────────────────────────────────────────────

def get_embedding_provider() -> EmbeddingProvider:
    """
    Factory: returns the configured EmbeddingProvider singleton.

    To add a new provider:
      1. Subclass EmbeddingProvider.
      2. Add an elif branch below with the provider key.
      3. Set EMBEDDING_PROVIDER=<key> in .env.
    """
    provider = settings.EMBEDDING_PROVIDER.lower()

    if provider == "gemini":
        return GeminiEmbeddingProvider(
            model=settings.EMBEDDING_MODEL,
            output_dims=settings.EMBEDDING_DIMENSIONS,
        )

    # ── Future providers (uncomment & implement when needed) ──────────────────
    # elif provider == "openai":
    #     return OpenAIEmbeddingProvider(model=settings.EMBEDDING_MODEL, ...)
    # elif provider == "cohere":
    #     return CohereEmbeddingProvider(model=settings.EMBEDDING_MODEL, ...)

    raise ValueError(
        f"Unknown EMBEDDING_PROVIDER='{provider}'. "
        f"Supported: 'gemini'. Add new providers in embedding.py."
    )
