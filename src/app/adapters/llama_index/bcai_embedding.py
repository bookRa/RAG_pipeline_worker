"""Boeing Conversational AI (BCAI) Embedding adapter for LlamaIndex.

This adapter wraps the BCAI Embedding API to work with LlamaIndex's embedding interface.
BCAI supports various embedding models including OpenAI and Tanzu models.

Supported Models:
- text-embedding-3-small
- text-embedding-3-large
- text-embedding-ada-002
- all-MiniLM-L6-v2-us-sovereign
- nomic-us-sovereign
"""

from __future__ import annotations

from typing import Any, Sequence

import requests

try:
    from llama_index.core.base.embeddings.base import BaseEmbedding, Embedding
except ImportError:  # pragma: no cover - optional dependency
    raise ImportError(
        "llama-index-core is required for BCAI adapter. "
        "Install with: pip install llama-index-core"
    )


class BCAIEmbedding(BaseEmbedding):
    """Boeing Conversational AI (BCAI) Embedding adapter.
    
    This adapter provides a LlamaIndex-compatible interface to the BCAI Embedding API,
    which supports multiple embedding models.
    
    Args:
        api_base: Base URL for BCAI API (e.g., "https://bcai-test.web.boeing.com")
        api_key: BCAI API key (UDAL PAT)
        model: Embedding model name (e.g., "text-embedding-3-small")
        dimensions: Optional dimensions override (only for text-embedding-3 models)
        timeout: Request timeout in seconds
        max_retries: Maximum number of retries on failure
        batch_size: Number of texts to embed in a single request
    """

    def __init__(
        self,
        *,
        api_base: str,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimensions: int | None = None,
        timeout: float = 60.0,
        max_retries: int = 2,
        batch_size: int = 10,
    ) -> None:
        super().__init__(model_name=model)
        self._api_base = api_base.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._dimensions = dimensions
        self._timeout = timeout
        self._max_retries = max_retries
        self._batch_size = batch_size
        
        # Setup session with authentication
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"basic {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        
        # Determine embedding dimension
        self._dimension = self._get_embedding_dimension()

    @property
    def dimension(self) -> int:  # type: ignore[override]
        """Return the embedding dimension."""
        return self._dimension

    def _get_embedding_dimension(self) -> int:
        """Determine the embedding dimension for the model."""
        # If dimensions explicitly provided, use that
        if self._dimensions:
            return self._dimensions
        
        # Default dimensions for known models
        dimension_map = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
            "all-MiniLM-L6-v2-us-sovereign": 384,
            "nomic-us-sovereign": 768,
        }
        return dimension_map.get(self._model, 1536)

    def _get_query_embedding(self, query: str) -> Embedding:
        """Get embedding for a single query text.
        
        Args:
            query: Text to embed
            
        Returns:
            Embedding vector as list of floats
        """
        return self._embed_single(query)

    async def _aget_query_embedding(self, query: str) -> Embedding:
        """Async get query embedding (uses sync implementation)."""
        return self._get_query_embedding(query)

    def _get_text_embedding(self, text: str) -> Embedding:
        """Get embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector as list of floats
        """
        return self._embed_single(text)

    async def _aget_text_embedding(self, text: str) -> Embedding:
        """Async get text embedding (uses sync implementation)."""
        return self._get_text_embedding(text)

    def _get_text_embeddings(self, texts: list[str]) -> list[Embedding]:
        """Get embeddings for multiple texts.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        # Batch texts to respect API limits and batch size
        all_embeddings: list[Embedding] = []
        
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i:i + self._batch_size]
            batch_embeddings = self._embed_batch(batch)
            all_embeddings.extend(batch_embeddings)
        
        return all_embeddings

    async def _aget_text_embeddings(self, texts: list[str]) -> list[Embedding]:
        """Async get text embeddings (uses sync implementation)."""
        return self._get_text_embeddings(texts)

    def _embed_single(self, text: str) -> Embedding:
        """Embed a single text."""
        embeddings = self._embed_batch([text])
        return embeddings[0]

    def _embed_batch(self, texts: list[str]) -> list[Embedding]:
        """Embed a batch of texts using BCAI API.
        
        Args:
            texts: List of texts to embed (max per BCAI limits)
            
        Returns:
            List of embedding vectors
            
        Raises:
            RuntimeError: If API call fails after retries
        """
        payload: dict[str, Any] = {
            "input": texts if len(texts) > 1 else texts[0],
            "model": self._model,
        }
        
        # Add dimensions if specified (only for text-embedding-3 models)
        if self._dimensions and "text-embedding-3" in self._model:
            payload["dimensions"] = self._dimensions
        
        url = f"{self._api_base}/bcai-public-api/embedding"
        
        # Retry logic
        last_exception = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._session.post(
                    url,
                    json=payload,
                    timeout=self._timeout,
                )
                response.raise_for_status()
                
                data = response.json()
                return self._extract_embeddings(data)
                
            except requests.exceptions.RequestException as exc:
                last_exception = exc
                if attempt == self._max_retries:
                    break
                # Wait before retrying (exponential backoff)
                import time
                time.sleep(2 ** attempt)
        
        raise RuntimeError(
            f"BCAI Embedding API error after {self._max_retries + 1} attempts: {last_exception}"
        ) from last_exception

    def _extract_embeddings(self, data: dict[str, Any]) -> list[Embedding]:
        """Extract embeddings from BCAI response.
        
        BCAI response format (same as OpenAI):
        {
            "data": [
                {"embedding": [0.1, 0.2, ...], "index": 0},
                {"embedding": [0.3, 0.4, ...], "index": 1},
            ],
            "model": "text-embedding-3-small",
            "usage": {"prompt_tokens": 10, "total_tokens": 10}
        }
        
        Args:
            data: API response JSON
            
        Returns:
            List of embedding vectors, sorted by index
        """
        try:
            embedding_data = data.get("data", [])
            if not embedding_data:
                raise ValueError("No embeddings in response")
            
            # Sort by index to ensure correct order
            sorted_data = sorted(embedding_data, key=lambda x: x.get("index", 0))
            
            return [item["embedding"] for item in sorted_data]
        except (KeyError, ValueError, TypeError) as exc:
            raise RuntimeError(f"Failed to extract embeddings from response: {exc}") from exc

