from __future__ import annotations

from random import Random

from ..domain.models import Document
from ..observability.logger import log_event


class VectorService:
    """Creates deterministic placeholder vectors for chunks."""

    def __init__(self, dimension: int = 8, seed: int = 42) -> None:
        self.dimension = dimension
        self.random = Random(seed)

    def _vector_for_text(self, text: str) -> list[float]:
        self.random.seed(hash(text) & 0xFFFFFFFF)
        return [round(self.random.random(), 3) for _ in range(self.dimension)]

    def vectorize(self, document: Document) -> Document:
        vector_attached = 0
        sample_vectors: list[dict[str, object]] = []
        for page in document.pages:
            for chunk in page.chunks:
                vector = self._vector_for_text(chunk.text)
                if chunk.metadata:
                    chunk.metadata.extra["vector"] = vector
                    chunk.metadata.extra["vector_dimension"] = self.dimension
                vector_attached += 1
                if len(sample_vectors) < 3:
                    sample_vectors.append({"chunk_id": chunk.id, "vector": vector})

        document.metadata["vector_dimension"] = self.dimension
        document.status = "vectorized"
        log_event(
            stage="vectorization",
            details={
                "document_id": document.id,
                "chunk_vectors": vector_attached,
                "dimension": self.dimension,
            },
        )
        document.metadata["vector_samples"] = sample_vectors
        return document
