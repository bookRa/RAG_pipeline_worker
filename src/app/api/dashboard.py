from __future__ import annotations

import os
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..domain.models import Document
from ..domain.run_models import PipelineRunRecord
from ..persistence.adapters.filesystem import FileSystemPipelineRunRepository
from ..services.chunking_service import ChunkingService
from ..services.cleaning_service import CleaningService
from ..services.enrichment_service import EnrichmentService
from ..services.extraction_service import ExtractionService
from ..services.ingestion_service import IngestionService
from ..services.pipeline_runner import PipelineRunner
from ..services.run_manager import PipelineRunManager
from ..services.vector_service import VectorService

BASE_DIR = Path(__file__).resolve().parents[3]
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

PIPELINE_STAGE_LATENCY = float(os.getenv("PIPELINE_STAGE_LATENCY", "0.05"))

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

ARTIFACTS_DIR = Path(
    os.getenv("RUN_ARTIFACTS_DIR", BASE_DIR / "artifacts" / "runs")
).resolve()
run_repository = FileSystemPipelineRunRepository(ARTIFACTS_DIR)
run_manager = PipelineRunManager(run_repository, pipeline_runner)
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
    runs = run_manager.list_runs(limit=MAX_RUNS_STORED)
    latest_run = runs[0] if runs else None
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "runs": runs,
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
    file.file.seek(0)
    stored_relative_path = _save_upload(file, run_id)

    run_record = run_manager.create_run(
        run_id=run_id,
        filename=file.filename,
        content_type=file.content_type,
        file_path=stored_relative_path,
        document=document,
    )

    run_manager.run_async(run_record, document, background_tasks)

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
    run = run_manager.get_run(run_id)
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
