from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..container import get_app_container
from ..domain.models import Document
from ..domain.run_models import PipelineRunRecord
from ..services.pipeline_runner import PipelineRunner
from ..services.run_manager import PipelineRunManager
from .task_scheduler import BackgroundTaskScheduler

BASE_DIR = Path(__file__).resolve().parents[3]
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
MAX_RUNS_STORED = 10


def _save_upload(file: UploadFile, run_id: str) -> str:
    suffix = Path(file.filename or "document").suffix
    safe_name = f"{run_id}{suffix}"
    destination = UPLOAD_DIR / safe_name
    with destination.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return f"uploads/{safe_name}"


def get_run_manager() -> PipelineRunManager:
    return get_app_container().pipeline_run_manager


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, run_manager: PipelineRunManager = Depends(get_run_manager)) -> HTMLResponse:
    runs = run_manager.list_runs(limit=MAX_RUNS_STORED)
    latest_run = runs[0] if runs else None
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "runs": runs,
            "latest_run": latest_run,
            "run": latest_run,
            "stage_sequence": list(PipelineRunner.STAGE_SEQUENCE),
        },
    )


@router.post("/upload", response_class=HTMLResponse)
async def dashboard_upload(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    run_manager: PipelineRunManager = Depends(get_run_manager),
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

    scheduler = BackgroundTaskScheduler(background_tasks)
    run_manager.run_async(run_record, document, scheduler, file_bytes=file_bytes)

    return templates.TemplateResponse(
        request,
        "partials/run_details.html",
        {
            "run": run_record,
            "stage_sequence": list(PipelineRunner.STAGE_SEQUENCE),
        },
    )


@router.get("/runs/{run_id}/fragment", response_class=HTMLResponse)
async def dashboard_run_fragment(
    request: Request,
    run_id: str,
    run_manager: PipelineRunManager = Depends(get_run_manager),
) -> HTMLResponse:
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


@router.get("/review", response_class=HTMLResponse)
async def review_page(request: Request) -> HTMLResponse:
    """Display the segment review queue page."""
    return templates.TemplateResponse(request, "review.html", {})
