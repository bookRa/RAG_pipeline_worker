from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..application.interfaces import VectorStoreAdapter


class InMemoryVectorStore(VectorStoreAdapter):
    """Development-friendly vector store that keeps vectors in memory."""

    def __init__(self) -> None:
        self._store: dict[str, list[Mapping[str, Any]]] = {}

    def upsert_chunks(self, document_id: str, vectors: Sequence[Mapping[str, Any]]) -> None:  # noqa: D401
        self._store[document_id] = list(vectors)

    def delete_document(self, document_id: str) -> None:  # noqa: D401
        self._store.pop(document_id, None)

    def get_vectors(self, document_id: str) -> list[Mapping[str, Any]]:
        return list(self._store.get(document_id, []))
