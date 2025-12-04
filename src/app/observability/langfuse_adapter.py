from __future__ import annotations

import logging
from typing import Any, Mapping

from ..application.interfaces import ObservabilityRecorder

logger = logging.getLogger(__name__)


class LangfuseObservabilityRecorder(ObservabilityRecorder):
    """Adapter that writes structured events to Langfuse spans."""

    def __init__(self, langfuse_handler: Any) -> None:
        """Initialize with a Langfuse callback handler.
        
        Args:
            langfuse_handler: LlamaIndexCallbackHandler instance from langfuse.llama_index
        """
        self._handler = langfuse_handler
        self._current_span = None

    def record_event(
        self,
        stage: str,
        details: Mapping[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> None:
        """Record event as a Langfuse span.
        
        Args:
            stage: Name of the pipeline stage
            details: Optional structured details about the event
            trace_id: Optional trace ID (if provided, will try to find existing trace)
        """
        if not self._handler or not hasattr(self._handler, 'langfuse'):
            logger.warning("Langfuse handler not available, skipping event recording")
            return

        try:
            langfuse_client = self._handler.langfuse
            
            # If trace_id is provided, try to find existing trace
            if trace_id:
                try:
                    # Create a span under the existing trace
                    trace = langfuse_client.trace(id=trace_id)
                    span = trace.span(
                        name=stage,
                        input=details or {},
                    )
                    if details:
                        span.update(output=details)
                except Exception as exc:
                    logger.warning("Failed to create span for trace_id %s: %s", trace_id, exc)
                    # Fallback: create standalone span
                    self._create_standalone_span(stage, details)
            else:
                # Create standalone span
                self._create_standalone_span(stage, details)
        except Exception as exc:
            logger.warning("Failed to record Langfuse event for stage %s: %s", stage, exc)

    def _create_standalone_span(self, stage: str, details: Mapping[str, Any] | None = None) -> None:
        """Create a standalone span (not linked to a trace)."""
        try:
            langfuse_client = self._handler.langfuse
            span = langfuse_client.span(
                name=stage,
                input=details or {},
            )
            if details:
                span.update(output=details)
        except Exception as exc:
            logger.warning("Failed to create standalone span for stage %s: %s", stage, exc)

