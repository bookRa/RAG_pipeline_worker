from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from src.app.domain.models import Document
from src.app.domain.run_models import PipelineResult, PipelineRunRecord, PipelineStage
from src.app.persistence.ports import DocumentRepository, PipelineRunRepository
from src.app.services.pipeline_runner import PipelineRunner
from src.app.services.run_manager import PipelineRunManager


class ImmediateScheduler:
    def __init__(self) -> None:
        self.scheduled = False

    def schedule(self, func):
        self.scheduled = True
        func()


class StubPipelineRunner(PipelineRunner):
    """Minimal stand-in that reuses PipelineRunner signature but not behavior."""

    def __init__(self, result: PipelineResult, raise_exc: bool = False) -> None:
        self._result = result
        self._raise = raise_exc
        # super().__init__ is not called because we only need the run method

    def run(
        self,
        document: Document,
        *,
        file_bytes: bytes | None = None,
        progress_callback=None,
    ) -> PipelineResult:
        if self._raise:
            raise RuntimeError("runner failed")
        if progress_callback:
            for stage in self._result.stages:
                progress_callback(stage, document)
        return self._result


class FakePipelineRunRepository(PipelineRunRepository):
    def __init__(self) -> None:
        self.started: list[PipelineRunRecord] = []
        self.updated: list[tuple[str, PipelineStage]] = []
        self.completed: list[str] = []
        self.failed: list[str] = []
        self.runs: dict[str, PipelineRunRecord] = {}

    def start_run(self, run: PipelineRunRecord) -> None:
        self.started.append(run)
        self.runs[run.id] = run

    def update_stage(self, run_id: str, stage: PipelineStage, document: Document | None = None) -> None:
        self.updated.append((run_id, stage))

    def complete_run(self, run_id: str, result: PipelineResult) -> None:
        self.completed.append(run_id)
        self.runs[run_id].result = result
        self.runs[run_id].status = "completed"

    def fail_run(self, run_id: str, error_message: str) -> None:
        self.failed.append(error_message)
        self.runs[run_id].status = "failed"

    def get_run(self, run_id: str) -> PipelineRunRecord | None:
        return self.runs.get(run_id)

    def list_runs(self, limit: int = 10) -> list[PipelineRunRecord]:
        return list(self.runs.values())[:limit]


class FakeDocumentRepository(DocumentRepository):
    def __init__(self) -> None:
        self.saved: list[Document] = []

    def save(self, document: Document) -> None:
        self.saved.append(document)

    def get(self, document_id: str) -> Document | None:  # pragma: no cover - not used
        for doc in self.saved:
            if doc.id == document_id:
                return doc
        return None

    def list(self) -> list[Document]:  # pragma: no cover - not used
        return list(self.saved)


def build_result() -> PipelineResult:
    document = Document(filename="demo.pdf", file_type="pdf")
    stage = PipelineStage(name="ingestion", title="Ingestion", details={"status": "ingested"})
    return PipelineResult(document=document, stages=[stage])


def build_run_record(document: Document) -> PipelineRunRecord:
    return PipelineRunRecord(
        id="run-1",
        created_at=datetime.utcnow(),
        filename=document.filename,
        content_type="application/pdf",
        file_path="uploads/demo.pdf",
        document=document,
    )


def test_run_manager_run_async_persists_updates_and_document():
    result = build_result()
    fake_repo = FakePipelineRunRepository()
    fake_doc_repo = FakeDocumentRepository()
    runner = StubPipelineRunner(result)
    manager = PipelineRunManager(fake_repo, runner, document_repository=fake_doc_repo)
    run_record = build_run_record(result.document)
    fake_repo.start_run(run_record)

    scheduler = ImmediateScheduler()
    manager.run_async(run_record, result.document, scheduler)

    assert fake_repo.completed == [run_record.id]
    assert fake_repo.updated
    assert fake_doc_repo.saved and fake_doc_repo.saved[0].id == result.document.id


def test_run_manager_run_async_handles_failures():
    result = build_result()
    fake_repo = FakePipelineRunRepository()
    manager = PipelineRunManager(fake_repo, StubPipelineRunner(result, raise_exc=True))
    run_record = build_run_record(result.document)
    fake_repo.start_run(run_record)

    scheduler = ImmediateScheduler()
    manager.run_async(run_record, result.document, scheduler)

    assert fake_repo.failed
    assert fake_repo.get_run(run_record.id).status == "failed"


def test_run_manager_run_sync_saves_document():
    result = build_result()
    fake_repo = FakePipelineRunRepository()
    fake_doc_repo = FakeDocumentRepository()
    runner = StubPipelineRunner(result)
    manager = PipelineRunManager(fake_repo, runner, document_repository=fake_doc_repo)

    outcome = manager.run_sync(result.document)

    assert outcome.document.id == result.document.id
    assert fake_doc_repo.saved and fake_doc_repo.saved[0].id == result.document.id
