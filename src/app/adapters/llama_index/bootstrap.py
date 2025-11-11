"""Helpers for configuring LlamaIndex globals from application settings.

These helpers keep all LlamaIndex imports inside the adapters layer so services
and domain code remain framework-agnostic. The application now always boots with
the LLM-backed pipeline, so importing this module should fail fast if the
expected dependencies are missing.
"""

from __future__ import annotations

import json
import os
from typing import Any

from ...config import Settings

_last_cache_key: tuple[str, ...] | None = None

try:  # Optional dependency – only needed when LlamaIndex is enabled.
    from llama_index.core import Settings as LlamaCoreSettings
    from llama_index.core.callbacks import CallbackManager, TokenCountingHandler
    from llama_index.core.node_parser import SentenceSplitter, TokenTextSplitter
except ImportError:  # pragma: no cover - optional dependency
    LlamaCoreSettings = None  # type: ignore[assignment]
    CallbackManager = None  # type: ignore[assignment]
    TokenCountingHandler = None  # type: ignore[assignment]
    SentenceSplitter = None  # type: ignore[assignment]
    TokenTextSplitter = None  # type: ignore[assignment]


class LlamaIndexBootstrapError(RuntimeError):
    """Raised when LlamaIndex configuration cannot be completed."""


def configure_llama_index(settings: Settings) -> None:
    """Configure global LlamaIndex settings based on application config."""

    if LlamaCoreSettings is None:
        raise LlamaIndexBootstrapError(
            "LlamaIndex packages are not installed. Install `llama-index-core` (and "
            "provider-specific extras) to continue."
        )

    cache_key = (
        json.dumps(settings.llm.model_dump(), sort_keys=True, default=str),
        json.dumps(settings.embeddings.model_dump(), sort_keys=True, default=str),
        json.dumps(settings.chunking.model_dump(), sort_keys=True, default=str),
        json.dumps(settings.vector_store.model_dump(), sort_keys=True, default=str),
        json.dumps(settings.prompts.model_dump(), sort_keys=True, default=str),
    )
    global _last_cache_key  # noqa: PLW0603
    if cache_key == _last_cache_key:
        return
    _configure_llama_index(settings)
    _last_cache_key = cache_key


def _configure_llama_index(settings: Settings) -> None:
    llm_client = _build_llm(settings)
    embed_model = _build_embedding(settings)
    text_splitter = _build_text_splitter(settings)
    callback_manager = _build_callback_manager()

    LlamaCoreSettings.llm = llm_client
    LlamaCoreSettings.embed_model = embed_model
    LlamaCoreSettings.text_splitter = text_splitter
    LlamaCoreSettings.chunk_size = settings.chunking.chunk_size
    LlamaCoreSettings.chunk_overlap = settings.chunking.chunk_overlap
    LlamaCoreSettings.callback_manager = callback_manager


def _build_llm(settings: Settings) -> Any:
    provider = settings.llm.provider
    if provider == "openai":
        try:
            from llama_index.llms.openai import OpenAI
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise LlamaIndexBootstrapError(
                "`settings.llm.provider` is set to 'openai' but "
                "`llama-index-llms-openai` is not installed."
            ) from exc

        api_key = settings.llm.api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise LlamaIndexBootstrapError(
                "OPENAI_API_KEY (or LLM__API_KEY) is required when using the OpenAI provider."
            )

        return OpenAI(
            model=settings.llm.model,
            temperature=settings.llm.temperature,
            api_base=settings.llm.api_base,
            api_key=api_key,
            timeout=settings.llm.timeout_seconds,
            max_retries=settings.llm.max_retries,
        )

    raise LlamaIndexBootstrapError(
        f"Unsupported LLM provider '{provider}'. Implement an adapter before enabling it."
    )


def _build_embedding(settings: Settings) -> Any:
    provider = settings.embeddings.provider
    if provider == "openai":
        try:
            from llama_index.embeddings.openai import OpenAIEmbedding
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise LlamaIndexBootstrapError(
                "`settings.embeddings.provider` is 'openai' but "
                "`llama-index-embeddings-openai` is not installed."
            ) from exc

        return OpenAIEmbedding(
            model=settings.embeddings.model,
            embed_batch_size=settings.embeddings.batch_size,
        )

    raise LlamaIndexBootstrapError(
        f"Unsupported embedding provider '{provider}'. Implement an adapter before enabling it."
    )


def _build_text_splitter(settings: Settings) -> Any:
    splitter = settings.chunking.splitter
    if splitter == "sentence":
        return SentenceSplitter(
            chunk_size=settings.chunking.chunk_size,
            chunk_overlap=settings.chunking.chunk_overlap,
        )
    if splitter == "token":
        return TokenTextSplitter(
            chunk_size=settings.chunking.chunk_size,
            chunk_overlap=settings.chunking.chunk_overlap,
        )
    raise LlamaIndexBootstrapError(
        f"Unsupported splitter '{splitter}'. Configure a custom splitter before enabling it."
    )


def _build_callback_manager() -> Any:
    if CallbackManager is None or TokenCountingHandler is None:
        return None
    token_counter = TokenCountingHandler()
    return CallbackManager([token_counter])


def get_llama_llm() -> Any:
    """Return the configured LLM instance."""

    if LlamaCoreSettings is None or getattr(LlamaCoreSettings, "llm", None) is None:
        raise LlamaIndexBootstrapError("LlamaIndex LLM has not been configured.")
    return LlamaCoreSettings.llm


def get_llama_embedding_model() -> Any:
    """Return the configured embedding model."""

    if LlamaCoreSettings is None or getattr(LlamaCoreSettings, "embed_model", None) is None:
        raise LlamaIndexBootstrapError("LlamaIndex embedding model has not been configured.")
    return LlamaCoreSettings.embed_model


def get_llama_text_splitter() -> Any:
    """Return the configured text splitter."""

    if LlamaCoreSettings is None or getattr(LlamaCoreSettings, "text_splitter", None) is None:
        raise LlamaIndexBootstrapError("LlamaIndex text splitter has not been configured.")
    return LlamaCoreSettings.text_splitter
