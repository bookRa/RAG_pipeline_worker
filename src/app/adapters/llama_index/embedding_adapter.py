from __future__ import annotations

from typing import Sequence

from ...application.interfaces import EmbeddingGenerator


class LlamaIndexEmbeddingAdapter(EmbeddingGenerator):
    """Adapter that delegates embedding generation to LlamaIndex models."""

    def __init__(self, embed_model: object, dimension: int) -> None:
        self._embed_model = embed_model
        self._dimension = dimension

    @property
    def dimension(self) -> int:  # noqa: D401
        return getattr(self._embed_model, "dimension", self._dimension)

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        embeddings: list[list[float]] = []
        for text in texts:
            cleaned = text.strip()
            if not cleaned:
                embeddings.append([0.0] * self.dimension)
                continue
            vector = self._embed_model.get_text_embedding(cleaned)
            embeddings.append([float(x) for x in vector])
        return embeddings
