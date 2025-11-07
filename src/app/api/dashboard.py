from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..domain.models import Document
from ..services.chunking_service import ChunkingService
from ..services.cleaning_service import CleaningService
from ..services.enrichment_service import EnrichmentService
from ..services.extraction_service import ExtractionService
from ..services.ingestion_service import IngestionService
from ..services.pipeline_runner import PipelineResult, PipelineRunner, PipelineStage
from ..services.vector_service import VectorService

BASE_DIR = Path(__file__).resolve().parents[3]
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

PIPELINE_STAGE_LATENCY = float(os.getenv("PIPELINE_STAGE_LATENCY", "0"))

ingestion_service = IngestionService(latency=PIPELINE_STAGE_LATENCY)
extraction_service = ExtractionService(latency=PIPELINE_STAGE_LATENCY)
cleaning_service = CleaningService(latency=PIPELINE_STAGE_LATENCY)
chunking_service = ChunkingService(latency=PIPELINE_STAGE_LATENCY)
enrichment_service = EnrichmentService(latency=PIPELINE_STAGE_LATENCY)
vector_service = VectorService(latency=PIPELINE_STAGE_LATENCY)
pipeline_runner = PipelineRunner(
    ingestion=ingestion_service,
    extraction=extraction_service,
    cleaning=cleaning_service,
    chunking=chunking_service,
    enrichment=enrichment_service,
    vectorization=vector_service,
)


@dataclass
class PipelineRunRecord:
    id: str
    created_at: datetime
    filename: str
    content_type: str | None
    file_path: str | None
    document: Document | None
    status: str = "running"
    stage_map: dict[str, PipelineStage] = field(default_factory=dict)
    result: PipelineResult | None = None
    error_message: str | None = None

    def update_stage(self, stage: PipelineStage) -> None:
        self.stage_map[stage.name] = stage

    def get_stage(self, name: str) -> PipelineStage | None:
        return self.stage_map.get(name)

    @property
    def page_count(self) -> int:
        return len(self.document.pages) if self.document else 0


PIPELINE_RUNS: list[PipelineRunRecord] = []
PIPELINE_RUNS_INDEX: dict[str, PipelineRunRecord] = {}
MAX_RUNS_STORED = 10


def _save_upload(file: UploadFile, run_id: str) -> str:
    suffix = Path(file.filename or "document").suffix
    safe_name = f"{run_id}{suffix}"
    destination = UPLOAD_DIR / safe_name
    with destination.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return f"uploads/{safe_name}"


def _register_run(run_record: PipelineRunRecord) -> None:
    PIPELINE_RUNS.append(run_record)
    PIPELINE_RUNS_INDEX[run_record.id] = run_record
    if len(PIPELINE_RUNS) > MAX_RUNS_STORED:
        removed = PIPELINE_RUNS.pop(0)
        PIPELINE_RUNS_INDEX.pop(removed.id, None)


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    latest_run = PIPELINE_RUNS[-1] if PIPELINE_RUNS else None
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "runs": list(reversed(PIPELINE_RUNS)),
            "latest_run": latest_run,
            "stage_sequence": list(PipelineRunner.STAGE_SEQUENCE),
        },
    )


@router.post("/upload", response_class=HTMLResponse)
async def dashboard_upload(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> HTMLResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    extension = file.filename.rsplit(".", 1)[-1].lower()
    if extension not in {"pdf", "docx", "ppt", "pptx"}:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    file_bytes = await file.read()
    document = Document(
        filename=file.filename,
        file_type=extension,
        size_bytes=len(file_bytes),
        metadata={"content_type": file.content_type},
    )

    run_id = str(uuid4())
    # Need to reset file pointer before saving since we read bytes already
    file.file.seek(0)
    stored_relative_path = _save_upload(file, run_id)

    run_record = PipelineRunRecord(
        id=run_id,
        created_at=datetime.utcnow(),
        filename=file.filename,
        content_type=file.content_type,
        file_path=stored_relative_path,
        document=document,
    )
    _register_run(run_record)

    def progress_callback(stage: PipelineStage, updated_document: Document) -> None:
        run_record.update_stage(stage)
        run_record.document = updated_document

    def execute_pipeline() -> None:
        try:
            result = pipeline_runner.run(document, progress_callback=progress_callback)
            run_record.result = result
            run_record.document = result.document
            run_record.status = "completed"
        except Exception as exc:
            run_record.status = "failed"
            run_record.error_message = str(exc)

    background_tasks.add_task(execute_pipeline)

    return templates.TemplateResponse(
        request,
        "partials/run_details.html",
        {
            "run": run_record,
            "stage_sequence": list(PipelineRunner.STAGE_SEQUENCE),
        },
    )


@router.get("/runs/{run_id}/fragment", response_class=HTMLResponse)
async def dashboard_run_fragment(request: Request, run_id: str) -> HTMLResponse:
    run = PIPELINE_RUNS_INDEX.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return templates.TemplateResponse(
        request,
        "partials/run_details.html",
        {
            "run": run,
            "stage_sequence": list(PipelineRunner.STAGE_SEQUENCE),
        },
    )
