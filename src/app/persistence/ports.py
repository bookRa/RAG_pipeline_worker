from __future__ import annotations

from typing import Protocol

from ..domain.models import Document
from ..domain.run_models import PipelineResult, PipelineRunRecord, PipelineStage


class PipelineRunRepository(Protocol):
    """Port defining how pipeline runs are persisted."""

    def start_run(self, run: PipelineRunRecord) -> None:
        """Persist a new run placeholder."""

    def update_stage(self, run_id: str, stage: PipelineStage, document: Document | None = None) -> None:
        """Persist a stage update and optional document snapshot."""

    def complete_run(self, run_id: str, result: PipelineResult) -> None:
        """Mark the run as completed and store the final artifact."""

    def fail_run(self, run_id: str, error_message: str) -> None:
        """Mark the run as failed with the given reason."""

    def get_run(self, run_id: str) -> PipelineRunRecord | None:
        """Fetch a run with its current metadata."""

    def list_runs(self, limit: int = 10) -> list[PipelineRunRecord]:
        """Return the most recent runs for dashboard display."""


class IngestionRepository(Protocol):
    """Port describing how raw uploads are stored."""

    def store(self, *, document_id: str, filename: str, data: bytes) -> str:
        """Persist the upload and return a stable path/identifier."""
