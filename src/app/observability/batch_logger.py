"""Specialized observability recorder for batch processing with cleaner logging and Langfuse integration."""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime
from typing import Any, Mapping

from ..application.interfaces import ObservabilityRecorder

logger = logging.getLogger("batch_pipeline")


class BatchObservabilityRecorder(ObservabilityRecorder):
    """Clean, minimal logging for batch processing with Langfuse integration.
    
    Provides:
    - Concise progress updates (e.g., "pixmap page 1 document.pdf")
    - Granular timestamps for each step
    - Multi-process/thread identification
    - Langfuse tracing with batch_id and document_job_id
    """

    def __init__(
        self,
        batch_id: str | None = None,
        document_job_id: str | None = None,
        langfuse_handler=None,
        enable_verbose: bool = False,
    ) -> None:
        """Initialize batch observability recorder.
        
        Args:
            batch_id: Batch identifier for grouping traces
            document_job_id: Document job identifier within the batch
            langfuse_handler: Optional Langfuse callback handler for tracing
            enable_verbose: Enable verbose JSON logging (default: False for clean logs)
        """
        self.batch_id = batch_id
        self.document_job_id = document_job_id
        self.langfuse_handler = langfuse_handler
        self.enable_verbose = enable_verbose
        self._trace = None
        self._current_spans: dict[str, Any] = {}
        
        # Configure logger for clean output, respecting centralized LOG_LEVEL
        from .logging_setup import get_log_level_from_settings
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s.%(msecs)03d | %(message)s",
                datefmt="%H:%M:%S"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        # Use centralized log level from settings
        logger.setLevel(get_log_level_from_settings())

    def record_event(self, stage: str, details: Mapping[str, Any] | None = None) -> None:
        """Record event with clean, minimal logging format."""
        details = details or {}
        
        # Get process/thread info for multi-process tracking
        process_id = os.getpid()
        thread_id = threading.get_ident()
        thread_name = threading.current_thread().name
        
        # Extract key information for clean logging
        document_id = details.get("document_id", "")
        filename = details.get("filename", "")
        page_number = details.get("page_number")
        page_count = details.get("page_count")
        
        # Format clean progress message
        msg_parts = []
        
        # Add stage
        msg_parts.append(f"[{stage.upper()}]")
        
        # Add batch/document context
        if self.batch_id:
            msg_parts.append(f"batch={self.batch_id[:8]}")
        if self.document_job_id:
            msg_parts.append(f"job={self.document_job_id[:8]}")
        
        # Add document context
        if filename:
            msg_parts.append(f"doc={filename}")
        elif document_id:
            msg_parts.append(f"doc={document_id[:8]}")
        
        # Add page context if relevant
        if page_number is not None:
            if page_count:
                msg_parts.append(f"page={page_number}/{page_count}")
            else:
                msg_parts.append(f"page={page_number}")
        
        # Add process/thread info for parallel tracking
        if thread_name != "MainThread":
            msg_parts.append(f"thread={thread_name}")
        
        # Add key metrics based on stage
        if stage == "pixmap_generation":
            total = details.get("total_generated", 0)
            if total:
                msg_parts.append(f"✓ {total} pages")
        elif stage == "parsing":
            components = details.get("component_count")
            if components:
                msg_parts.append(f"{components} components")
        elif stage == "cleaning":
            tokens = details.get("cleaned_tokens")
            if tokens:
                msg_parts.append(f"{tokens} tokens")
        elif stage == "chunking":
            chunks = details.get("chunk_count")
            if chunks:
                msg_parts.append(f"{chunks} chunks")
        elif stage == "enrichment":
            has_summary = details.get("has_document_summary")
            if has_summary:
                msg_parts.append("✓ summary")
        elif stage == "vectorization":
            vectors = details.get("vector_count")
            if vectors:
                msg_parts.append(f"{vectors} vectors")
        elif stage == "pipeline_complete":
            duration = details.get("duration_ms")
            if duration:
                msg_parts.append(f"⏱ {duration:.0f}ms")
        
        # Log clean message
        message = " ".join(msg_parts)
        logger.info(message)
        
        # Optionally log verbose JSON (disabled by default for batch)
        if self.enable_verbose and details:
            logger.debug(f"  └─ {details}")
        
        # Send to Langfuse if available
        if self.langfuse_handler:
            self._record_to_langfuse(stage, details)

    def start_trace(self, name: str, input_data: dict[str, Any]) -> None:
        """Start a Langfuse trace for a pipeline run.
        
        Args:
            name: Trace name (e.g., "batch_document_processing" or "document_pipeline::file.pdf")
            input_data: Input data to log
        """
        if not self.langfuse_handler:
            return
        
        try:
            # Extract file_type and document_id from input_data
            file_type = input_data.get("file_type")
            document_id = input_data.get("document_id")
            
            metadata = {
                "batch_id": self.batch_id,
                "document_job_id": self.document_job_id,
                "process_id": os.getpid(),
                "thread_id": threading.get_ident(),
            }
            
            # Build tags consistent with single-file pipeline
            tags = ["pipeline"]
            if file_type:
                tags.append(file_type)
            if self.batch_id:
                tags.append("batch")
                tags.append(self.batch_id[:8])  # Short batch ID for filtering
            
            # Set trace parameters on the handler BEFORE creating trace
            # This ensures LlamaIndex LLM calls use these parameters
            if hasattr(self.langfuse_handler, "set_trace_params"):
                try:
                    self.langfuse_handler.set_trace_params(
                        name=name,
                        session_id=self.batch_id or document_id,
                        metadata=metadata,
                        tags=tags,
                    )
                except Exception as e:
                    logger.warning(f"Failed to set trace params: {e}")
            
            # Create the trace
            self._trace = self.langfuse_handler.langfuse.trace(
                name=name,
                session_id=self.batch_id or document_id,
                input=input_data,
                metadata=metadata,
                tags=tags,
            )
            
            # CRITICAL: Set this as the root trace for all subsequent LlamaIndex LLM calls
            # This ensures all LLM operations (parsing, cleaning, enrichment) are nested
            # under this document trace instead of creating separate top-level traces
            if hasattr(self.langfuse_handler, "set_root"):
                try:
                    self.langfuse_handler.set_root(self._trace, update_root=False)
                except Exception as e:
                    logger.warning(f"Failed to set root trace: {e}")
                    
        except Exception as e:
            logger.warning(f"Failed to start Langfuse trace: {e}")

    def start_span(self, name: str, input_data: dict[str, Any] | None = None) -> None:
        """Start a span within the current trace.
        
        Args:
            name: Span name (e.g., "parsing", "cleaning")
            input_data: Optional input data
        """
        if not self._trace:
            return
        
        try:
            span = self._trace.span(
                name=name,
                input=input_data or {},
                metadata={
                    "batch_id": self.batch_id,
                    "document_job_id": self.document_job_id,
                }
            )
            self._current_spans[name] = span
        except Exception as e:
            logger.warning(f"Failed to start Langfuse span {name}: {e}")

    def end_span(self, name: str, output_data: dict[str, Any] | None = None) -> None:
        """End a span within the current trace.
        
        Args:
            name: Span name
            output_data: Optional output data
        """
        if name not in self._current_spans:
            return
        
        try:
            span = self._current_spans[name]
            if output_data:
                span.end(output=output_data)
            else:
                span.end()
            del self._current_spans[name]
        except Exception as e:
            logger.warning(f"Failed to end Langfuse span {name}: {e}")

    def end_trace(self, output_data: dict[str, Any] | None = None) -> None:
        """End the current trace.
        
        Args:
            output_data: Optional output data
        """
        if not self._trace:
            return
        
        try:
            if output_data:
                self._trace.update(output=output_data)
                
            # Clear the root trace from the handler so subsequent operations
            # don't accidentally nest under this closed trace
            if self.langfuse_handler and hasattr(self.langfuse_handler, "set_root"):
                try:
                    self.langfuse_handler.set_root(None, update_root=False)
                except Exception as e:
                    logger.warning(f"Failed to clear root trace: {e}")
                    
        except Exception as e:
            logger.warning(f"Failed to end Langfuse trace: {e}")
        finally:
            self._trace = None

    def _record_to_langfuse(self, stage: str, details: Mapping[str, Any]) -> None:
        """Record event data to Langfuse as a generation or event.
        
        This ensures all observability data sent to the standard logger
        is also sent to Langfuse for comprehensive tracing.
        """
        if not self._trace:
            return
        
        try:
            # Create a Langfuse generation (event) for this stage
            self._trace.generation(
                name=stage,
                input=details,
                output={"status": "completed"},
                metadata={
                    "batch_id": self.batch_id,
                    "document_job_id": self.document_job_id,
                    "process_id": os.getpid(),
                    "thread_id": threading.get_ident(),
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )
        except Exception as e:
            logger.warning(f"Failed to record event to Langfuse: {e}")


def create_batch_logger(
    batch_id: str | None = None,
    document_job_id: str | None = None,
    langfuse_handler=None,
) -> BatchObservabilityRecorder:
    """Factory function to create batch observability recorder.
    
    Args:
        batch_id: Batch identifier
        document_job_id: Document job identifier
        langfuse_handler: Optional Langfuse callback handler
        
    Returns:
        Configured BatchObservabilityRecorder instance
    """
    return BatchObservabilityRecorder(
        batch_id=batch_id,
        document_job_id=document_job_id,
        langfuse_handler=langfuse_handler,
        enable_verbose=False,  # Clean logs by default
    )







