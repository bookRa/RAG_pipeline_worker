"""Batch dashboard routes for testing and monitoring batch processing."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..container import get_app_container
from ..persistence.ports import BatchJobRepository

BASE_DIR = Path(__file__).resolve().parents[3]
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(prefix="/batch-dashboard", tags=["batch-dashboard"])


def get_batch_repository() -> BatchJobRepository:
    """Dependency for batch job repository."""
    return get_app_container().batch_job_repository


@router.get("/", response_class=HTMLResponse)
async def batch_dashboard(
    request: Request,
    repository: BatchJobRepository = Depends(get_batch_repository),
) -> HTMLResponse:
    """Render batch upload and monitoring interface.
    
    This dashboard provides:
    - Multiple file upload
    - Real-time progress monitoring via SSE
    - Per-document status tracking
    - Batch-level summary
    - History of recent batches
    """
    # Get recent batches for history
    recent_batches = repository.list_batches(limit=10)
    
    return templates.TemplateResponse(
        request,
        "batch_dashboard.html",
        {
            "recent_batches": recent_batches,
        },
    )


@router.get("/batches/{batch_id}", response_class=HTMLResponse)
async def batch_details_page(
    request: Request,
    batch_id: str,
    repository: BatchJobRepository = Depends(get_batch_repository),
) -> HTMLResponse:
    """Render detailed view of a specific batch.
    
    Args:
        request: FastAPI request object
        batch_id: Batch identifier
        repository: Batch repository dependency
        
    Returns:
        HTML response with batch details
    """
    batch = repository.get_batch(batch_id)
    
    return templates.TemplateResponse(
        request,
        "batch_details.html",
        {
            "batch": batch,
        },
    )







