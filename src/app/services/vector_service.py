from __future__ import annotations

import logging
import time
from random import Random
from typing import Sequence

from ..application.interfaces import EmbeddingGenerator, ObservabilityRecorder, VectorStoreAdapter
from ..domain.models import Document

logger = logging.getLogger(__name__)


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
        embedding_generator: EmbeddingGenerator | None = None,
        vector_store: VectorStoreAdapter | None = None,
        dimension: int = 8,
        seed: int = 42,
        latency: float = 0.0,
    ) -> None:
        self.observability = observability
        self.embedding_generator = embedding_generator
        self.vector_store = vector_store
        self.dimension = embedding_generator.dimension if embedding_generator else dimension
        self.random = Random(seed)
        self.latency = latency

    def _vector_for_text(self, text: str) -> list[float]:
        self.random.seed(hash(text) & 0xFFFFFFFF)
        return [round(self.random.random(), 3) for _ in range(self.dimension)]

    def _embed_batch(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        if self.embedding_generator:
            return self.embedding_generator.embed(texts)
        return [self._vector_for_text(text) for text in texts]

    def vectorize(self, document: Document) -> Document:
        if self.latency > 0:
            time.sleep(self.latency)
        
        logger.info(
            "🎨 Starting vectorization for doc=%s (%d dimension)",
            document.id,
            self.dimension,
        )
        
        vector_attached = 0
        contextualized_count = 0
        sample_vectors: list[dict[str, object]] = []
        updated_pages = []
        
        for page in document.pages:
            updated_chunks = []
            # Use contextualized_text for embedding (with context prefix)
            # Fall back to cleaned_text or raw text if contextualized_text is not available
            chunk_texts = [
                chunk.contextualized_text or chunk.cleaned_text or chunk.text or "" 
                for chunk in page.chunks
            ]
            
            # Log which chunks have contextualized text
            for chunk in page.chunks:
                if chunk.contextualized_text:
                    contextualized_count += 1
            
            embeddings = self._embed_batch(chunk_texts)
            for chunk, vector in zip(page.chunks, embeddings):
                
                if chunk.metadata:
                    updated_extra = chunk.metadata.extra.copy()
                    updated_extra["vector"] = vector
                    updated_extra["vector_dimension"] = self.dimension
                    updated_extra["used_contextualized_text"] = bool(chunk.contextualized_text)
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
        
        logger.info(
            "✅ Vectorization complete: %d vectors created, %d used contextualized text",
            vector_attached,
            contextualized_count,
        )

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
        
        if self.vector_store:
            payload = []
            for page in updated_pages:
                for chunk in page.chunks:
                    vector = []
                    if chunk.metadata and "vector" in chunk.metadata.extra:
                        vector = chunk.metadata.extra["vector"]
                    payload.append(
                        {
                            "chunk_id": chunk.id,
                            "page_number": chunk.page_number,
                            "vector": vector,
                            "metadata": chunk.metadata.model_dump() if chunk.metadata else {},
                        }
                    )
            self.vector_store.upsert_chunks(updated_document.id, payload)

        self.observability.record_event(
            stage="vectorization",
            details={
                "document_id": updated_document.id,
                "chunk_vectors": vector_attached,
                "dimension": self.dimension,
            },
        )
        return updated_document
