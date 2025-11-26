"""Batch pipeline runner for processing multiple documents in parallel."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable
from uuid import uuid4

from ..domain.batch_models import BatchJob, DocumentJob
from ..domain.models import Document
from ..observability.batch_logger import create_batch_logger
from ..persistence.ports import BatchJobRepository
from .parallel_page_processor import ParallelPageProcessor
from .pipeline_runner import PipelineRunner
from .run_manager import PipelineRunManager

logger = logging.getLogger(__name__)


class BatchPipelineRunner:
    """Coordinates parallel processing of multiple documents as a batch.
    
    This runner manages:
    1. Document-level parallelism: Process multiple documents concurrently
    2. Page-level parallelism: Within each document, process pages in parallel
    3. Rate limiting: Respect API limits across all parallel operations
    4. Progress tracking: Update batch and document job statuses
    5. Error handling: Continue or fail based on error strategy
    
    The runner uses asyncio for I/O-bound operations (LLM calls) and
    coordinates with ParallelPageProcessor for page-level parallelism.
    """

    def __init__(
        self,
        pipeline_runner: PipelineRunner,
        parallel_processor: ParallelPageProcessor,
        batch_repository: BatchJobRepository,
        run_manager: PipelineRunManager,
        max_concurrent_documents: int = 5,
        langfuse_handler: Any | None = None,
    ) -> None:
        """Initialize the batch pipeline runner.
        
        Args:
            pipeline_runner: Standard pipeline runner for sequential fallback
            parallel_processor: Processor for parallel page operations
            batch_repository: Repository for batch job persistence
            run_manager: Manager for individual pipeline runs
            max_concurrent_documents: Maximum documents to process simultaneously
            langfuse_handler: Optional Langfuse callback handler for tracing
        """
        self.runner = pipeline_runner
        self.parallel = parallel_processor
        self.batch_repo = batch_repository
        self.run_manager = run_manager
        self.max_concurrent = max_concurrent_documents
        self.langfuse_handler = langfuse_handler

    async def run_batch(
        self,
        batch_id: str,
        documents: list[tuple[Document, bytes]],
        progress_callback: Callable[[str, DocumentJob], None] | None = None,
    ) -> BatchJob:
        """Process multiple documents in parallel as a batch.
        
        Args:
            batch_id: Unique identifier for this batch
            documents: List of (Document, file_bytes) tuples to process
            progress_callback: Optional callback for progress updates (for SSE)
            
        Returns:
            Completed BatchJob with all document results
        """
        # Create clean batch logger
        batch_logger = create_batch_logger(
            batch_id=batch_id,
            langfuse_handler=self.langfuse_handler,
        )
        
        batch_logger.record_event(
            "batch_started",
            {
                "batch_id": batch_id,
                "total_documents": len(documents),
                "max_concurrent": self.max_concurrent,
            }
        )

        # Start Langfuse trace for batch
        batch_logger.start_trace(
            name="batch_document_processing",
            input_data={
                "batch_id": batch_id,
                "document_count": len(documents),
                "filenames": [doc.filename for doc, _ in documents],
            }
        )

        # Create batch job
        batch = BatchJob(
            id=batch_id,
            created_at=datetime.utcnow(),
            status="queued",
            total_documents=len(documents),
        )

        # Create document jobs for each document
        for document, _ in documents:
            doc_job = DocumentJob(
                document_id=document.id,
                filename=document.filename,
                status="queued",
            )
            batch.add_document_job(doc_job)

        # Persist initial batch state
        self.batch_repo.create_batch(batch)

        # Use semaphore to limit concurrent documents
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def process_single_document(
            document: Document,
            file_bytes: bytes,
        ) -> tuple[str, bool, str | None]:
            """Process a single document through the pipeline.
            
            Returns:
                Tuple of (document_id, success, error_message)
            """
            doc_job = batch.document_jobs[document.id]
            
            # Create document-specific logger
            doc_logger = create_batch_logger(
                batch_id=batch_id,
                document_job_id=document.id,
                langfuse_handler=self.langfuse_handler,
            )
            
            # Start document-level trace
            doc_logger.start_trace(
                name="document_pipeline",
                input_data={
                    "document_id": document.id,
                    "filename": document.filename,
                    "file_type": document.file_type,
                    "size_bytes": document.size_bytes,
                }
            )

            async with semaphore:
                start_time = datetime.utcnow()
                
                try:
                    # Mark document as processing
                    doc_job.mark_stage_started("ingestion")
                    self.batch_repo.update_document_job(batch_id, doc_job)
                    
                    if progress_callback:
                        progress_callback(batch_id, doc_job)

                    # Create a pipeline run for this document
                    run_id = str(uuid4())
                    run_record = self.run_manager.create_run(
                        run_id=run_id,
                        filename=document.filename,
                        content_type=document.metadata.get("content_type"),
                        file_path=None,
                        document=document,
                    )
                    doc_job.run_id = run_id

                    # Process through pipeline stages
                    # Ingestion
                    doc_logger.start_span("ingestion", {"filename": document.filename})
                    doc_logger.record_event("ingestion_started", {
                        "document_id": document.id,
                        "filename": document.filename,
                    })
                    
                    document = self.runner.ingestion.ingest(
                        document,
                        file_bytes=file_bytes,
                    )
                    doc_job.mark_stage_completed("ingestion")
                    self.batch_repo.update_document_job(batch_id, doc_job)
                    
                    doc_logger.end_span("ingestion", {"page_count": len(document.pages)})
                    doc_logger.record_event("ingestion", {
                        "document_id": document.id,
                        "filename": document.filename,
                        "page_count": len(document.pages),
                    })
                    
                    if progress_callback:
                        progress_callback(batch_id, doc_job)

                    # Parsing (with parallel page processing)
                    doc_job.mark_stage_started("parsing")
                    self.batch_repo.update_document_job(batch_id, doc_job)
                    
                    if progress_callback:
                        progress_callback(batch_id, doc_job)

                    doc_logger.start_span("parsing", {"page_count": len(document.pages)})
                    
                    if self.parallel.enable:
                        # Pass document logger to parallel processor for page-level logging
                        document = await self.parallel.parse_pages_parallel(
                            document,
                            file_bytes,
                            doc_logger=doc_logger,
                        )
                    else:
                        loop = asyncio.get_event_loop()
                        document = await loop.run_in_executor(
                            None,
                            self.runner.parsing.parse,
                            document,
                            file_bytes,
                        )

                    doc_job.mark_stage_completed("parsing")
                    self.batch_repo.update_document_job(batch_id, doc_job)
                    
                    doc_logger.end_span("parsing", {"pages_parsed": len(document.pages)})
                    doc_logger.record_event("parsing", {
                        "document_id": document.id,
                        "filename": document.filename,
                        "page_count": len(document.pages),
                    })
                    
                    if progress_callback:
                        progress_callback(batch_id, doc_job)

                    # Cleaning (with parallel page processing)
                    doc_job.mark_stage_started("cleaning")
                    self.batch_repo.update_document_job(batch_id, doc_job)
                    
                    if progress_callback:
                        progress_callback(batch_id, doc_job)

                    doc_logger.start_span("cleaning", {"page_count": len(document.pages)})
                    
                    if self.parallel.enable:
                        document = await self.parallel.clean_pages_parallel(
                            document,
                            doc_logger=doc_logger,
                        )
                    else:
                        loop = asyncio.get_event_loop()
                        document = await loop.run_in_executor(
                            None,
                            self.runner.cleaning.clean,
                            document,
                        )

                    doc_job.mark_stage_completed("cleaning")
                    self.batch_repo.update_document_job(batch_id, doc_job)
                    
                    doc_logger.end_span("cleaning", {"pages_cleaned": len(document.pages)})
                    doc_logger.record_event("cleaning", {
                        "document_id": document.id,
                        "filename": document.filename,
                        "page_count": len(document.pages),
                    })
                    
                    if progress_callback:
                        progress_callback(batch_id, doc_job)

                    # Chunking
                    doc_job.mark_stage_started("chunking")
                    self.batch_repo.update_document_job(batch_id, doc_job)
                    
                    if progress_callback:
                        progress_callback(batch_id, doc_job)
                    
                    doc_logger.start_span("chunking")

                    loop = asyncio.get_event_loop()
                    document = await loop.run_in_executor(
                        None,
                        self.runner.chunking.chunk,
                        document,
                    )

                    doc_job.mark_stage_completed("chunking")
                    self.batch_repo.update_document_job(batch_id, doc_job)
                    
                    doc_logger.end_span("chunking", {"chunk_count": len(document.chunks)})
                    doc_logger.record_event("chunking", {
                        "document_id": document.id,
                        "filename": document.filename,
                        "chunk_count": len(document.chunks),
                    })
                    
                    if progress_callback:
                        progress_callback(batch_id, doc_job)

                    # Enrichment
                    doc_job.mark_stage_started("enrichment")
                    self.batch_repo.update_document_job(batch_id, doc_job)
                    
                    if progress_callback:
                        progress_callback(batch_id, doc_job)

                    doc_logger.start_span("enrichment")
                    
                    document = await loop.run_in_executor(
                        None,
                        self.runner.enrichment.enrich,
                        document,
                    )

                    doc_job.mark_stage_completed("enrichment")
                    self.batch_repo.update_document_job(batch_id, doc_job)
                    
                    doc_logger.end_span("enrichment", {
                        "has_document_summary": bool(document.metadata.get("summary"))
                    })
                    doc_logger.record_event("enrichment", {
                        "document_id": document.id,
                        "filename": document.filename,
                        "has_document_summary": bool(document.metadata.get("summary")),
                    })
                    
                    if progress_callback:
                        progress_callback(batch_id, doc_job)

                    # Vectorization
                    doc_job.mark_stage_started("vectorization")
                    self.batch_repo.update_document_job(batch_id, doc_job)
                    
                    if progress_callback:
                        progress_callback(batch_id, doc_job)

                    doc_logger.start_span("vectorization")
                    
                    document = await loop.run_in_executor(
                        None,
                        self.runner.vectorization.vectorize,
                        document,
                    )

                    doc_job.mark_stage_completed("vectorization")
                    doc_job.mark_completed()
                    self.batch_repo.update_document_job(batch_id, doc_job)
                    
                    vector_count = sum(1 for chunk in document.chunks if chunk.embedding is not None)
                    doc_logger.end_span("vectorization", {"vector_count": vector_count})
                    doc_logger.record_event("vectorization", {
                        "document_id": document.id,
                        "filename": document.filename,
                        "vector_count": vector_count,
                    })
                    
                    if progress_callback:
                        progress_callback(batch_id, doc_job)

                    # Save final document
                    if self.run_manager.document_repository:
                        self.run_manager.document_repository.save(document)

                    # Calculate duration
                    duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                    
                    # End document trace
                    doc_logger.end_trace({
                        "status": "completed",
                        "chunk_count": len(document.chunks),
                        "duration_ms": duration_ms,
                    })
                    
                    doc_logger.record_event("pipeline_complete", {
                        "document_id": document.id,
                        "filename": document.filename,
                        "duration_ms": duration_ms,
                    })

                    return (document.id, True, None)

                except Exception as exc:
                    error_msg = str(exc)
                    
                    # End trace with error
                    doc_logger.end_trace({
                        "status": "failed",
                        "error": error_msg,
                    })
                    
                    doc_logger.record_event("pipeline_failed", {
                        "document_id": document.id,
                        "filename": document.filename,
                        "error": error_msg,
                    })
                    
                    doc_job.mark_failed(error_msg)
                    self.batch_repo.update_document_job(batch_id, doc_job)
                    
                    if progress_callback:
                        progress_callback(batch_id, doc_job)

                    return (document.id, False, error_msg)

        # Process all documents concurrently
        tasks = [
            process_single_document(doc, file_bytes)
            for doc, file_bytes in documents
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=False)

        # Update final batch status
        batch = self.batch_repo.get_batch(batch_id)
        if batch:
            batch.update_status()
            self.batch_repo.update_batch(batch)

        # End batch trace
        batch_logger.end_trace({
            "completed_documents": batch.completed_documents if batch else 0,
            "failed_documents": batch.failed_documents if batch else 0,
            "total_documents": batch.total_documents if batch else 0,
            "status": batch.status if batch else "failed",
        })
        
        batch_logger.record_event("batch_completed", {
            "batch_id": batch_id,
            "completed": batch.completed_documents if batch else 0,
            "failed": batch.failed_documents if batch else 0,
            "total": batch.total_documents if batch else 0,
        })

        return batch or BatchJob(
            id=batch_id,
            created_at=datetime.utcnow(),
            status="failed",
        )

