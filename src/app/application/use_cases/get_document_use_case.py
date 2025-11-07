from __future__ import annotations

from fastapi import HTTPException

from ...domain.models import Document
from ...persistence.ports import DocumentRepository


class GetDocumentUseCase:
    """Use case for retrieving a single document by ID."""

    def __init__(self, repository: DocumentRepository) -> None:
        self.repository = repository

    def execute(self, document_id: str) -> Document:
        """
        Execute the get document use case.

        Args:
            document_id: Unique identifier of the document

        Returns:
            Document instance

        Raises:
            HTTPException: If document is not found
        """
        document = self.repository.get(document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        return document

