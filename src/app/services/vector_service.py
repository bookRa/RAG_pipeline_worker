from __future__ import annotations

import time
from random import Random

from ..application.interfaces import ObservabilityRecorder
from ..domain.models import Document


class VectorService:
    """
    Creates placeholder vectors for chunks.
    
    This is a placeholder implementation that generates deterministic vectors using
    a simple hash-based approach. In production, this will be replaced with an
    embedding model adapter that implements a VectorGenerator port.
    
    The service follows hexagonal architecture principles:
    - Depends only on ObservabilityRecorder interface (port)
    - Returns immutable Document instances
    - Can be easily swapped with a real embedding service
    - Fully testable via dependency injection
    """

    def __init__(
        self,
        observability: ObservabilityRecorder,
        dimension: int = 8,
        seed: int = 42,
        latency: float = 0.0,
    ) -> None:
        self.observability = observability
        self.dimension = dimension
        self.random = Random(seed)
        self.latency = latency

    def _vector_for_text(self, text: str) -> list[float]:
        self.random.seed(hash(text) & 0xFFFFFFFF)
        return [round(self.random.random(), 3) for _ in range(self.dimension)]

    def vectorize(self, document: Document) -> Document:
        if self.latency > 0:
            time.sleep(self.latency)
        vector_attached = 0
        sample_vectors: list[dict[str, object]] = []
        updated_pages = []
        
        for page in document.pages:
            updated_chunks = []
            for chunk in page.chunks:
                vector = self._vector_for_text(chunk.text)
                
                if chunk.metadata:
                    updated_extra = chunk.metadata.extra.copy()
                    updated_extra["vector"] = vector
                    updated_extra["vector_dimension"] = self.dimension
                    updated_metadata = chunk.metadata.model_copy(update={"extra": updated_extra})
                    updated_chunk = chunk.model_copy(update={"metadata": updated_metadata})
                else:
                    updated_chunk = chunk
                
                updated_chunks.append(updated_chunk)
                vector_attached += 1
                if len(sample_vectors) < 3:
                    sample_vectors.append({"chunk_id": chunk.id, "vector": vector})
            
            updated_page = page.model_copy(update={"chunks": updated_chunks})
            updated_pages.append(updated_page)

        updated_metadata = document.metadata.copy()
        updated_metadata["vector_dimension"] = self.dimension
        updated_metadata["vector_samples"] = sample_vectors
        
        updated_document = document.model_copy(
            update={
                "pages": updated_pages,
                "status": "vectorized",
                "metadata": updated_metadata,
            }
        )
        
        self.observability.record_event(
            stage="vectorization",
            details={
                "document_id": updated_document.id,
                "chunk_vectors": vector_attached,
                "dimension": self.dimension,
            },
        )
        return updated_document
