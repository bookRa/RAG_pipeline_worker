from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from ..domain.models import Document
from ..domain.run_models import PipelineResult, PipelineRunRecord, PipelineStage
from ..persistence.ports import DocumentRepository, PipelineRunRepository
from ..application.interfaces import TaskScheduler
from .pipeline_runner import PipelineRunner


class PipelineRunManager:
    """Coordinates pipeline execution with persistence."""

    def __init__(
        self,
        repository: PipelineRunRepository,
        runner: PipelineRunner,
        document_repository: DocumentRepository | None = None,
    ) -> None:
        self.repository = repository
        self.runner = runner
        self.document_repository = document_repository

    def create_run(
        self,
        *,
        run_id: str | None = None,
        filename: str,
        content_type: str | None,
        file_path: str | None,
        document: Document,
    ) -> PipelineRunRecord:
        run_id = run_id or str(uuid4())
        record = PipelineRunRecord(
            id=run_id,
            created_at=datetime.utcnow(),
            filename=filename,
            content_type=content_type,
            file_path=file_path,
            document=document,
        )
        self.repository.start_run(record)
        return record

    def run_async(
        self,
        record: PipelineRunRecord,
        document: Document,
        scheduler: TaskScheduler,
        file_bytes: bytes | None = None,
    ) -> None:
        def progress_callback(stage: PipelineStage, updated_document: Document) -> None:
            self.repository.update_stage(record.id, stage, updated_document)

        def task() -> None:
            try:
                result = self.runner.run(
                    document,
                    file_bytes=file_bytes,
                    progress_callback=progress_callback,
                    run_id=record.id,
                )
                self.repository.complete_run(record.id, result)
                if self.document_repository:
                    self.document_repository.save(result.document)
            except Exception as exc:  # pragma: no cover - defensive
                self.repository.fail_run(record.id, str(exc))

        scheduler.schedule(task)

    def run_sync(self, document: Document, file_bytes: bytes | None = None) -> PipelineResult:
        result = self.runner.run(document, file_bytes=file_bytes, run_id=document.id)
        if self.document_repository:
            self.document_repository.save(result.document)
        return result

    def get_run(self, run_id: str) -> PipelineRunRecord | None:
        return self.repository.get_run(run_id)

    def list_runs(self, limit: int = 10) -> list[PipelineRunRecord]:
        return self.repository.list_runs(limit)
