"""Domain models for batch processing operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass
class DocumentJob:
    """Tracks processing of a single document within a batch.
    
    Each document in a batch has its own job that tracks its progress through
    the pipeline stages. This allows for independent failure handling and
    detailed progress tracking per document.
    
    Attributes:
        document_id: Unique identifier for the document being processed
        filename: Original filename of the uploaded document
        status: Current processing status (queued, processing, completed, failed)
        current_stage: Name of the current pipeline stage being executed
        error_message: Error details if the job failed
        run_id: Link to PipelineRunRecord for detailed stage information
        completed_stages: List of stage names that have been completed
        created_at: Timestamp when the job was created
        started_at: Timestamp when processing started
        completed_at: Timestamp when processing completed (success or failure)
    """
    
    document_id: str
    filename: str
    status: Literal["queued", "processing", "completed", "failed"] = "queued"
    current_stage: str | None = None
    error_message: str | None = None
    run_id: str | None = None
    completed_stages: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    
    def mark_stage_started(self, stage_name: str) -> None:
        """Mark a stage as started (mutates self for internal use)."""
        self.current_stage = stage_name
        if self.status == "queued":
            self.status = "processing"
            self.started_at = datetime.utcnow()
    
    def mark_stage_completed(self, stage_name: str) -> None:
        """Mark a stage as completed (mutates self for internal use)."""
        if stage_name not in self.completed_stages:
            self.completed_stages.append(stage_name)
    
    def mark_completed(self) -> None:
        """Mark the entire job as completed (mutates self for internal use)."""
        self.status = "completed"
        self.completed_at = datetime.utcnow()
        self.current_stage = None
    
    def mark_failed(self, error: str) -> None:
        """Mark the job as failed (mutates self for internal use)."""
        self.status = "failed"
        self.error_message = error
        self.completed_at = datetime.utcnow()


@dataclass
class BatchJob:
    """Tracks processing of multiple documents as a cohesive batch.
    
    A batch job coordinates the processing of multiple documents, providing
    both aggregate metrics and individual document tracking. Supports both
    "fail_all" and "continue" error strategies.
    
    Attributes:
        id: Unique identifier for the batch
        created_at: Timestamp when the batch was created
        status: Overall batch status (queued, processing, completed, failed, partial)
        total_documents: Total number of documents in the batch
        completed_documents: Number of documents that completed successfully
        failed_documents: Number of documents that failed
        document_jobs: Mapping of document_id to DocumentJob
        error_strategy: How to handle individual document failures
        started_at: Timestamp when batch processing started
        completed_at: Timestamp when batch processing finished
    """
    
    id: str
    created_at: datetime
    status: Literal["queued", "processing", "completed", "failed", "partial"] = "queued"
    total_documents: int = 0
    completed_documents: int = 0
    failed_documents: int = 0
    document_jobs: dict[str, DocumentJob] = field(default_factory=dict)
    error_strategy: Literal["fail_all", "continue"] = "continue"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    
    @property
    def progress_percentage(self) -> float:
        """Calculate progress as a percentage (0-100)."""
        if self.total_documents == 0:
            return 0.0
        processed = self.completed_documents + self.failed_documents
        return (processed / self.total_documents) * 100
    
    @property
    def is_finished(self) -> bool:
        """Check if the batch has finished processing (success, failure, or partial)."""
        return self.status in ("completed", "failed", "partial")
    
    def add_document_job(self, doc_job: DocumentJob) -> None:
        """Add a document job to the batch (mutates self for internal use)."""
        self.document_jobs[doc_job.document_id] = doc_job
        self.total_documents = len(self.document_jobs)
    
    def update_status(self) -> None:
        """Update batch status based on document job states (mutates self for internal use)."""
        if not self.document_jobs:
            return
        
        # Count document statuses
        queued = sum(1 for job in self.document_jobs.values() if job.status == "queued")
        processing = sum(1 for job in self.document_jobs.values() if job.status == "processing")
        completed = sum(1 for job in self.document_jobs.values() if job.status == "completed")
        failed = sum(1 for job in self.document_jobs.values() if job.status == "failed")
        
        self.completed_documents = completed
        self.failed_documents = failed
        
        # Start batch if any document is processing
        if self.status == "queued" and processing > 0:
            self.status = "processing"
            self.started_at = datetime.utcnow()
        
        # Determine overall status
        total_finished = completed + failed
        if total_finished == self.total_documents:
            # All documents finished
            if failed == 0:
                self.status = "completed"
            elif completed == 0:
                self.status = "failed"
            else:
                self.status = "partial"
            self.completed_at = datetime.utcnow()
        elif failed > 0 and self.error_strategy == "fail_all":
            # Fail entire batch if any document fails (and strategy is fail_all)
            self.status = "failed"
            self.completed_at = datetime.utcnow()







