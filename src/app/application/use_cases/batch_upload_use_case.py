"""Use case for batch document upload and processing."""

from __future__ import annotations

import asyncio
from datetime import datetime
from uuid import uuid4

from fastapi import HTTPException

from ...domain.batch_models import BatchJob, DocumentJob
from ...domain.models import Document
from ...persistence.ports import BatchJobRepository
from ...services.batch_pipeline_runner import BatchPipelineRunner

ALLOWED_EXTENSIONS = {"pdf", "docx", "ppt", "pptx"}


class BatchUploadUseCase:
    """Use case for uploading and processing multiple documents as a batch.
    
    This use case:
    1. Validates all uploaded files
    2. Creates a BatchJob with DocumentJobs for tracking
    3. Schedules batch processing asynchronously
    4. Returns batch metadata immediately (non-blocking)
    
    The actual processing happens in the background, and clients can
    monitor progress via the batch status API or SSE streaming endpoint.
    """

    def __init__(
        self,
        batch_runner: BatchPipelineRunner,
        batch_repository: BatchJobRepository,
    ) -> None:
        """Initialize the batch upload use case.
        
        Args:
            batch_runner: Runner for parallel batch processing
            batch_repository: Repository for batch job persistence
        """
        self.batch_runner = batch_runner
        self.batch_repository = batch_repository

    def execute(
        self,
        files: list[tuple[str, str, bytes, str | None]],  # (filename, file_type, file_bytes, content_type)
        error_strategy: str = "continue",
    ) -> BatchJob:
        """Execute batch document upload and schedule processing.
        
        Args:
            files: List of (filename, file_type, file_bytes, content_type) tuples
            error_strategy: How to handle failures ("continue" or "fail_all")
            
        Returns:
            BatchJob with queued status (processing happens async)
            
        Raises:
            HTTPException: If validation fails for any file
        """
        if not files:
            raise HTTPException(status_code=400, detail="No files provided")

        if len(files) > 50:
            raise HTTPException(
                status_code=400,
                detail=f"Too many files ({len(files)}). Maximum is 50.",
            )

        # Validate error strategy
        if error_strategy not in ("continue", "fail_all"):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid error_strategy: {error_strategy}. Must be 'continue' or 'fail_all'.",
            )

        # Validate all files first (fail fast before creating batch)
        documents: list[tuple[Document, bytes]] = []
        
        for filename, file_type, file_bytes, content_type in files:
            # Validate filename
            if not filename:
                raise HTTPException(status_code=400, detail="All files must have filenames")

            # Validate file extension
            extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else file_type.lower()
            if extension not in ALLOWED_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported file type: {extension}. Allowed: {ALLOWED_EXTENSIONS}",
                )

            # Create Document instance
            document = Document(
                filename=filename,
                file_type=extension,
                size_bytes=len(file_bytes),
                metadata={"content_type": content_type} if content_type else {},
            )
            
            documents.append((document, file_bytes))

        # Create batch job
        batch_id = str(uuid4())
        batch = BatchJob(
            id=batch_id,
            created_at=datetime.utcnow(),
            status="queued",
            total_documents=len(documents),
            error_strategy=error_strategy,  # type: ignore
        )

        # Add document jobs
        for document, _ in documents:
            doc_job = DocumentJob(
                document_id=document.id,
                filename=document.filename,
                status="queued",
            )
            batch.add_document_job(doc_job)

        # Persist batch
        self.batch_repository.create_batch(batch)

        # Schedule batch processing in background
        # Note: This runs in a separate asyncio task, so it doesn't block the response
        asyncio.create_task(
            self._run_batch_async(batch_id, documents)
        )

        return batch

    async def _run_batch_async(
        self,
        batch_id: str,
        documents: list[tuple[Document, bytes]],
    ) -> None:
        """Run batch processing asynchronously in background.
        
        This is called via asyncio.create_task() and runs independently
        of the HTTP request lifecycle.
        """
        try:
            await self.batch_runner.run_batch(
                batch_id=batch_id,
                documents=documents,
                progress_callback=None,  # No callback for background processing
            )
        except Exception as exc:
            # Log error but don't raise (background task)
            import logging
            logger = logging.getLogger(__name__)
            logger.error("Batch processing failed: batch_id=%s, error=%s", batch_id, exc)
            
            # Mark batch as failed
            batch = self.batch_repository.get_batch(batch_id)
            if batch:
                batch.status = "failed"
                self.batch_repository.update_batch(batch)







