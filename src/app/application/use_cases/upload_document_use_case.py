from __future__ import annotations

from fastapi import HTTPException

from ...domain.models import Document
from ...persistence.ports import DocumentRepository
from ...services.pipeline_runner import PipelineRunner

ALLOWED_EXTENSIONS = {"pdf", "docx", "ppt", "pptx"}


class UploadDocumentUseCase:
    """Use case for uploading and processing a document."""

    def __init__(self, runner: PipelineRunner, repository: DocumentRepository) -> None:
        self.runner = runner
        self.repository = repository

    def execute(self, filename: str, file_type: str, file_bytes: bytes, content_type: str | None = None) -> Document:
        """
        Execute the upload document use case.

        Args:
            filename: Name of the uploaded file
            file_type: File extension (pdf, docx, ppt, pptx)
            file_bytes: Raw file content
            content_type: MIME type of the file (optional)

        Returns:
            Processed Document instance

        Raises:
            HTTPException: If filename is missing or file type is not supported
        """
        if not filename:
            raise HTTPException(status_code=400, detail="Filename is required")

        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else file_type.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail="Unsupported file type")

        document = Document(
            filename=filename,
            file_type=extension,
            size_bytes=len(file_bytes),
            metadata={"content_type": content_type} if content_type else {},
        )

        result = self.runner.run(document, file_bytes=file_bytes)
        processed_document = result.document
        self.repository.save(processed_document)
        return processed_document

