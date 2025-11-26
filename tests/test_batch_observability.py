"""Tests for batch observability and logging."""

import pytest

from src.app.observability.batch_logger import (
    BatchObservabilityRecorder,
    create_batch_logger,
)


class TestBatchObservabilityRecorder:
    """Tests for BatchObservabilityRecorder."""

    def test_create_batch_logger(self):
        """Test creating a batch logger."""
        logger = create_batch_logger(
            batch_id="test-batch-123",
            document_job_id="doc-job-456",
        )
        
        assert logger.batch_id == "test-batch-123"
        assert logger.document_job_id == "doc-job-456"
        assert logger.enable_verbose is False

    def test_record_event_minimal_format(self, caplog):
        """Test that events are logged in minimal format."""
        logger = create_batch_logger(
            batch_id="batch-123",
            document_job_id="doc-456",
        )
        
        logger.record_event("pixmap_generation", {
            "document_id": "doc-123",
            "filename": "test.pdf",
            "total_generated": 10,
            "page_count": 10,
        })
        
        # Should log with minimal format, not verbose JSON
        assert "batch=batch-12" in caplog.text  # Shortened batch ID
        assert "job=doc-456" in caplog.text  # Shortened job ID
        assert "doc=test.pdf" in caplog.text
        assert "✓ 10 pages" in caplog.text

    def test_record_event_with_page_number(self, caplog):
        """Test logging with page number."""
        logger = create_batch_logger(batch_id="batch-123")
        
        logger.record_event("pixmap_page_complete", {
            "document_id": "doc-123",
            "filename": "test.pdf",
            "page_number": 5,
            "page_count": 10,
        })
        
        assert "page=5/10" in caplog.text
        assert "doc=test.pdf" in caplog.text

    def test_record_event_parsing_stage(self, caplog):
        """Test logging parsing stage."""
        logger = create_batch_logger()
        
        logger.record_event("parsing", {
            "document_id": "doc-123",
            "filename": "test.pdf",
            "page_count": 5,
            "component_count": 42,
        })
        
        assert "[PARSING]" in caplog.text
        assert "42 components" in caplog.text

    def test_record_event_cleaning_stage(self, caplog):
        """Test logging cleaning stage."""
        logger = create_batch_logger()
        
        logger.record_event("cleaning", {
            "filename": "test.pdf",
            "cleaned_tokens": 1234,
        })
        
        assert "[CLEANING]" in caplog.text
        assert "1234 tokens" in caplog.text

    def test_record_event_chunking_stage(self, caplog):
        """Test logging chunking stage."""
        logger = create_batch_logger()
        
        logger.record_event("chunking", {
            "filename": "test.pdf",
            "chunk_count": 45,
        })
        
        assert "[CHUNKING]" in caplog.text
        assert "45 chunks" in caplog.text

    def test_record_event_enrichment_stage(self, caplog):
        """Test logging enrichment stage."""
        logger = create_batch_logger()
        
        logger.record_event("enrichment", {
            "filename": "test.pdf",
            "has_document_summary": True,
        })
        
        assert "[ENRICHMENT]" in caplog.text
        assert "✓ summary" in caplog.text

    def test_record_event_vectorization_stage(self, caplog):
        """Test logging vectorization stage."""
        logger = create_batch_logger()
        
        logger.record_event("vectorization", {
            "filename": "test.pdf",
            "vector_count": 45,
        })
        
        assert "[VECTORIZATION]" in caplog.text
        assert "45 vectors" in caplog.text

    def test_record_event_pipeline_complete(self, caplog):
        """Test logging pipeline complete."""
        logger = create_batch_logger()
        
        logger.record_event("pipeline_complete", {
            "filename": "test.pdf",
            "duration_ms": 18789.5,
        })
        
        assert "[PIPELINE_COMPLETE]" in caplog.text
        assert "⏱ 18790ms" in caplog.text  # Rounded

    def test_start_and_end_trace_without_langfuse(self):
        """Test that trace methods work without Langfuse configured."""
        logger = create_batch_logger()
        
        # Should not raise errors
        logger.start_trace("test_trace", {"input": "data"})
        logger.start_span("test_span", {"span_input": "data"})
        logger.end_span("test_span", {"span_output": "data"})
        logger.end_trace({"output": "data"})

    def test_verbose_mode_disabled_by_default(self):
        """Test that verbose mode is disabled by default for batch logger."""
        logger = create_batch_logger()
        assert logger.enable_verbose is False

    def test_langfuse_handler_none_by_default(self):
        """Test that langfuse_handler is None by default."""
        logger = create_batch_logger()
        assert logger.langfuse_handler is None

    def test_custom_batch_and_job_ids(self):
        """Test custom batch and job IDs."""
        logger = create_batch_logger(
            batch_id="custom-batch-id",
            document_job_id="custom-job-id",
        )
        
        assert logger.batch_id == "custom-batch-id"
        assert logger.document_job_id == "custom-job-id"

