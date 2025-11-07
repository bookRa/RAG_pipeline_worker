from __future__ import annotations

from ..domain.models import Document
from ..persistence.ports import DocumentRepository


class ListDocumentsUseCase:
    """Use case for listing all documents."""

    def __init__(self, repository: DocumentRepository) -> None:
        self.repository = repository

    def execute(self) -> list[Document]:
        """
        Execute the list documents use case.

        Returns:
            List of all documents in the repository
        """
        return self.repository.list()

