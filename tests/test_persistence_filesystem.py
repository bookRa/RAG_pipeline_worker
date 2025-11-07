from pathlib import Path

from src.app.domain.models import Document
from src.app.domain.run_models import PipelineRunRecord, PipelineStage
from src.app.persistence.adapters.filesystem import FileSystemPipelineRunRepository
from src.app.services.pipeline_runner import PipelineResult


def test_filesystem_repository_persists_runs(tmp_path: Path):
    repo = FileSystemPipelineRunRepository(tmp_path)
    document = Document(filename="demo.pdf", file_type="pdf", size_bytes=10)
    run = PipelineRunRecord(
        id="run-123",
        created_at=document.uploaded_at,
        filename="demo.pdf",
        content_type="application/pdf",
        file_path="uploads/demo.pdf",
        document=document,
    )

    repo.start_run(run)

    stage = PipelineStage(name="ingestion", title="Ingestion", details={"status": "ingested"})
    repo.update_stage(run.id, stage, document)

    result = PipelineResult(document=document, stages=[stage])
    repo.complete_run(run.id, result)

    loaded = repo.get_run(run.id)
    assert loaded is not None
    assert loaded.status == "completed"
    assert loaded.get_stage("ingestion") is not None
    assert loaded.document is not None

    runs = repo.list_runs()
    assert runs and runs[0].id == run.id
