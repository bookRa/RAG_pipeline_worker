"""Integration test for Ragas evaluation with Langfuse traces.

This module demonstrates how to fetch traces from Langfuse and score them with Ragas metrics.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

try:
    from langfuse import Langfuse
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False

try:
    from ragas.metrics import answer_relevancy, faithfulness
    RAGAS_AVAILABLE = True
except ImportError:
    RAGAS_AVAILABLE = False

# Note: Ragas-Langfuse integration may not be available in all versions
# This is a placeholder for when the integration becomes available
try:
    from ragas.integrations.langfuse import langfuse_evaluate
    RAGAS_LANGFUSE_INTEGRATION_AVAILABLE = True
except ImportError:
    RAGAS_LANGFUSE_INTEGRATION_AVAILABLE = False
    # Define a placeholder function if integration is not available
    def langfuse_evaluate(*args, **kwargs):
        """Placeholder for Ragas-Langfuse integration when not available."""
        print("Ragas-Langfuse integration not available. Skipping evaluation.")
        return None

from src.app.config import settings


def evaluate_langfuse_traces():
    """Fetch traces from Langfuse and score them with Ragas metrics."""
    if not LANGFUSE_AVAILABLE:
        print("Langfuse is not installed. Skipping trace evaluation.")
        return
    
    if not RAGAS_AVAILABLE:
        print("Ragas is not installed. Skipping trace evaluation.")
        return
    
    if not settings.enable_langfuse:
        print("Langfuse is not enabled. Skipping trace evaluation.")
        return
    
    if not RAGAS_LANGFUSE_INTEGRATION_AVAILABLE:
        print("Ragas-Langfuse integration is not available in this version.")
        print("This feature requires ragas with langfuse integration support.")
        return
    
    # Initialize Langfuse client
    langfuse = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )
    
    # Fetch traces from the last 24 hours
    traces = langfuse.fetch_traces(
        name="rag_query",  # Adjust based on your trace naming
        from_timestamp=datetime.now() - timedelta(days=1),
        limit=100,
    )
    
    if not traces:
        print("No traces found in Langfuse.")
        return
    
    print(f"Found {len(traces)} traces to evaluate")
    
    # Score traces with Ragas metrics
    langfuse_evaluate(
        langfuse=langfuse,
        traces=traces,
        metrics=[faithfulness, answer_relevancy],
    )
    
    print("Traces scored and stored in Langfuse UI")


if __name__ == "__main__":
    evaluate_langfuse_traces()

