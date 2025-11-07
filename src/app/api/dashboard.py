from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..domain.models import Document
from ..services.chunking_service import ChunkingService
from ..services.cleaning_service import CleaningService
from ..services.enrichment_service import EnrichmentService
from ..services.extraction_service import ExtractionService
from ..services.ingestion_service import IngestionService
from ..services.pipeline_runner import PipelineResult, PipelineRunner
from ..services.vector_service import VectorService

BASE_DIR = Path(__file__).resolve().parents[3]
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

ingestion_service = IngestionService()
extraction_service = ExtractionService()
cleaning_service = CleaningService()
chunking_service = ChunkingService()
enrichment_service = EnrichmentService()
vector_service = VectorService()
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
    result: PipelineResult

    @property
    def document(self) -> Document:
        return self.result.document

    @property
    def page_count(self) -> int:
        return len(self.document.pages)


PIPELINE_RUNS: list[PipelineRunRecord] = []
MAX_RUNS_STORED = 10


def _save_upload(file: UploadFile, run_id: str) -> str:
    suffix = Path(file.filename or "document").suffix
    safe_name = f"{run_id}{suffix}"
    destination = UPLOAD_DIR / safe_name
    with destination.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return f"uploads/{safe_name}"


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    latest_run = PIPELINE_RUNS[-1] if PIPELINE_RUNS else None
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "runs": list(reversed(PIPELINE_RUNS)),
            "latest_run": latest_run,
        },
    )


@router.post("/upload", response_class=HTMLResponse)
async def dashboard_upload(request: Request, file: UploadFile = File(...)) -> HTMLResponse:
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

    result = pipeline_runner.run(document)
    run_record = PipelineRunRecord(
        id=run_id,
        created_at=datetime.utcnow(),
        filename=file.filename,
        content_type=file.content_type,
        file_path=stored_relative_path,
        result=result,
    )
    PIPELINE_RUNS.append(run_record)
    if len(PIPELINE_RUNS) > MAX_RUNS_STORED:
        PIPELINE_RUNS.pop(0)

    return templates.TemplateResponse(
        request,
        "partials/run_details.html",
        {
            "run": run_record,
        },
    )
