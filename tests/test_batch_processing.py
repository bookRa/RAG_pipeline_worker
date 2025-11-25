"""Tests for batch processing functionality."""

import asyncio
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

from src.app.domain.batch_models import BatchJob, DocumentJob
from src.app.domain.models import Document
from src.app.persistence.adapters.batch_filesystem import FileSystemBatchJobRepository


class TestBatchDomainModels:
    """Tests for batch domain models."""

    def test_document_job_creation(self):
        """Test creating a document job."""
        doc_job = DocumentJob(
            document_id="doc-123",
            filename="test.pdf",
        )
        
        assert doc_job.document_id == "doc-123"
        assert doc_job.filename == "test.pdf"
        assert doc_job.status == "queued"
        assert doc_job.current_stage is None
        assert doc_job.completed_stages == []

    def test_document_job_stage_progression(self):
        """Test document job stage progression."""
        doc_job = DocumentJob(
            document_id="doc-123",
            filename="test.pdf",
        )
        
        # Start first stage
        doc_job.mark_stage_started("ingestion")
        assert doc_job.status == "processing"
        assert doc_job.current_stage == "ingestion"
        assert doc_job.started_at is not None
        
        # Complete first stage
        doc_job.mark_stage_completed("ingestion")
        assert "ingestion" in doc_job.completed_stages
        
        # Start second stage
        doc_job.mark_stage_started("parsing")
        assert doc_job.current_stage == "parsing"
        
        # Complete second stage
        doc_job.mark_stage_completed("parsing")
        assert "parsing" in doc_job.completed_stages
        
        # Mark job completed
        doc_job.mark_completed()
        assert doc_job.status == "completed"
        assert doc_job.completed_at is not None
        assert doc_job.current_stage is None

    def test_document_job_failure(self):
        """Test document job failure."""
        doc_job = DocumentJob(
            document_id="doc-123",
            filename="test.pdf",
        )
        
        doc_job.mark_stage_started("parsing")
        doc_job.mark_failed("Parsing error: invalid PDF")
        
        assert doc_job.status == "failed"
        assert doc_job.error_message == "Parsing error: invalid PDF"
        assert doc_job.completed_at is not None

    def test_batch_job_creation(self):
        """Test creating a batch job."""
        batch = BatchJob(
            id="batch-123",
            created_at=datetime.utcnow(),
        )
        
        assert batch.id == "batch-123"
        assert batch.status == "queued"
        assert batch.total_documents == 0
        assert batch.completed_documents == 0
        assert batch.failed_documents == 0
        assert batch.error_strategy == "continue"

    def test_batch_job_add_documents(self):
        """Test adding document jobs to batch."""
        batch = BatchJob(
            id="batch-123",
            created_at=datetime.utcnow(),
        )
        
        doc_job_1 = DocumentJob(document_id="doc-1", filename="doc1.pdf")
        doc_job_2 = DocumentJob(document_id="doc-2", filename="doc2.pdf")
        
        batch.add_document_job(doc_job_1)
        batch.add_document_job(doc_job_2)
        
        assert batch.total_documents == 2
        assert "doc-1" in batch.document_jobs
        assert "doc-2" in batch.document_jobs

    def test_batch_job_status_updates(self):
        """Test batch job status updates based on document jobs."""
        batch = BatchJob(
            id="batch-123",
            created_at=datetime.utcnow(),
        )
        
        # Add 3 documents
        for i in range(3):
            doc_job = DocumentJob(document_id=f"doc-{i}", filename=f"doc{i}.pdf")
            batch.add_document_job(doc_job)
        
        # All queued
        batch.update_status()
        assert batch.status == "queued"
        
        # One processing
        batch.document_jobs["doc-0"].mark_stage_started("parsing")
        batch.update_status()
        assert batch.status == "processing"
        
        # One completed
        batch.document_jobs["doc-0"].mark_completed()
        batch.update_status()
        assert batch.status == "processing"
        assert batch.completed_documents == 1
        
        # Two completed
        batch.document_jobs["doc-1"].mark_stage_started("parsing")
        batch.document_jobs["doc-1"].mark_completed()
        batch.update_status()
        assert batch.status == "processing"
        assert batch.completed_documents == 2
        
        # All completed
        batch.document_jobs["doc-2"].mark_stage_started("parsing")
        batch.document_jobs["doc-2"].mark_completed()
        batch.update_status()
        assert batch.status == "completed"
        assert batch.completed_documents == 3
        assert batch.is_finished

    def test_batch_job_partial_failure(self):
        """Test batch job with partial failures (continue strategy)."""
        batch = BatchJob(
            id="batch-123",
            created_at=datetime.utcnow(),
            error_strategy="continue",
        )
        
        # Add 3 documents
        for i in range(3):
            doc_job = DocumentJob(document_id=f"doc-{i}", filename=f"doc{i}.pdf")
            batch.add_document_job(doc_job)
        
        # Complete two, fail one
        batch.document_jobs["doc-0"].mark_completed()
        batch.document_jobs["doc-1"].mark_failed("Error")
        batch.document_jobs["doc-2"].mark_completed()
        
        batch.update_status()
        assert batch.status == "partial"
        assert batch.completed_documents == 2
        assert batch.failed_documents == 1
        assert batch.is_finished

    def test_batch_job_progress_percentage(self):
        """Test batch job progress percentage calculation."""
        batch = BatchJob(
            id="batch-123",
            created_at=datetime.utcnow(),
        )
        
        # Add 4 documents
        for i in range(4):
            doc_job = DocumentJob(document_id=f"doc-{i}", filename=f"doc{i}.pdf")
            batch.add_document_job(doc_job)
        
        assert batch.progress_percentage == 0.0
        
        # Complete 2
        batch.document_jobs["doc-0"].mark_completed()
        batch.document_jobs["doc-1"].mark_completed()
        batch.update_status()
        assert batch.progress_percentage == 50.0
        
        # Complete all
        batch.document_jobs["doc-2"].mark_completed()
        batch.document_jobs["doc-3"].mark_completed()
        batch.update_status()
        assert batch.progress_percentage == 100.0


class TestBatchRepository:
    """Tests for batch job repository."""

    def test_create_and_get_batch(self, tmp_path):
        """Test creating and retrieving a batch."""
        repo = FileSystemBatchJobRepository(tmp_path)
        
        batch = BatchJob(
            id="batch-123",
            created_at=datetime.utcnow(),
        )
        
        doc_job = DocumentJob(document_id="doc-1", filename="doc1.pdf")
        batch.add_document_job(doc_job)
        
        # Create
        repo.create_batch(batch)
        
        # Verify files exist
        assert (tmp_path / "batch-123" / "batch.json").exists()
        assert (tmp_path / "batch-123" / "documents" / "doc-1.json").exists()
        
        # Get
        retrieved = repo.get_batch("batch-123")
        assert retrieved is not None
        assert retrieved.id == "batch-123"
        assert retrieved.total_documents == 1
        assert "doc-1" in retrieved.document_jobs

    def test_update_batch(self, tmp_path):
        """Test updating an existing batch."""
        repo = FileSystemBatchJobRepository(tmp_path)
        
        batch = BatchJob(
            id="batch-123",
            created_at=datetime.utcnow(),
        )
        
        doc_job = DocumentJob(document_id="doc-1", filename="doc1.pdf")
        batch.add_document_job(doc_job)
        repo.create_batch(batch)
        
        # Update document job
        doc_job.mark_stage_started("parsing")
        doc_job.mark_completed()
        batch.update_status()
        
        repo.update_batch(batch)
        
        # Retrieve and verify
        retrieved = repo.get_batch("batch-123")
        assert retrieved is not None
        assert retrieved.status == "completed"
        assert retrieved.document_jobs["doc-1"].status == "completed"

    def test_update_document_job(self, tmp_path):
        """Test updating a specific document job."""
        repo = FileSystemBatchJobRepository(tmp_path)
        
        batch = BatchJob(
            id="batch-123",
            created_at=datetime.utcnow(),
        )
        
        doc_job = DocumentJob(document_id="doc-1", filename="doc1.pdf")
        batch.add_document_job(doc_job)
        repo.create_batch(batch)
        
        # Update just the document job
        doc_job.mark_stage_started("parsing")
        repo.update_document_job("batch-123", doc_job)
        
        # Retrieve and verify
        retrieved = repo.get_batch("batch-123")
        assert retrieved is not None
        assert retrieved.document_jobs["doc-1"].status == "processing"
        assert retrieved.document_jobs["doc-1"].current_stage == "parsing"

    def test_list_batches(self, tmp_path):
        """Test listing recent batches."""
        repo = FileSystemBatchJobRepository(tmp_path)
        
        # Create 3 batches
        for i in range(3):
            batch = BatchJob(
                id=f"batch-{i}",
                created_at=datetime.utcnow(),
            )
            repo.create_batch(batch)
        
        # List
        batches = repo.list_batches(limit=10)
        assert len(batches) == 3

    def test_get_nonexistent_batch(self, tmp_path):
        """Test getting a batch that doesn't exist."""
        repo = FileSystemBatchJobRepository(tmp_path)
        
        result = repo.get_batch("nonexistent")
        assert result is None


@pytest.mark.asyncio
class TestRateLimiter:
    """Tests for rate limiter."""

    async def test_rate_limiter_basic(self):
        """Test basic rate limiting."""
        from src.app.services.rate_limiter import RateLimiter
        
        # Allow 60 requests per minute (1 per second)
        limiter = RateLimiter(requests_per_minute=60)
        
        # First request should be immediate
        await limiter.acquire(1)
        
        # Second request should wait ~1 second
        # (we'll just verify it doesn't raise an error)
        await limiter.acquire(1)

    async def test_rate_limiter_burst(self):
        """Test burst capacity."""
        from src.app.services.rate_limiter import RateLimiter
        
        # Allow 60 requests per minute with burst of 10
        limiter = RateLimiter(requests_per_minute=60, burst_size=10)
        
        # First 10 requests should be immediate (burst)
        for _ in range(10):
            await limiter.acquire(1)

    async def test_rate_limiter_context_manager(self):
        """Test using rate limiter as context manager."""
        from src.app.services.rate_limiter import RateLimiter
        
        limiter = RateLimiter(requests_per_minute=60)
        
        async with limiter:
            # Inside context, token is acquired
            pass


# Note: More comprehensive integration tests would require mocking LLM calls
# and testing the full batch pipeline, which is better suited for end-to-end tests


