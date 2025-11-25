"""Batch processing API endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sse_starlette.sse import EventSourceResponse

from ..application.use_cases.batch_upload_use_case import BatchUploadUseCase
from ..container import get_app_container
from ..domain.batch_models import BatchJob, DocumentJob
from ..persistence.ports import BatchJobRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/batch", tags=["batch"])


def get_batch_upload_use_case() -> BatchUploadUseCase:
    """Dependency for batch upload use case."""
    return get_app_container().batch_upload_use_case


def get_batch_repository() -> BatchJobRepository:
    """Dependency for batch job repository."""
    return get_app_container().batch_job_repository


@router.post("/upload")
async def batch_upload(
    files: list[UploadFile] = File(...),
    error_strategy: str = "continue",
    use_case: BatchUploadUseCase = Depends(get_batch_upload_use_case),
) -> dict:
    """Upload multiple documents for batch processing.
    
    This endpoint accepts multiple files and processes them in parallel.
    The response is returned immediately with a batch_id that can be used
    to monitor progress via the /batch/{batch_id} or /batch/{batch_id}/stream endpoints.
    
    Args:
        files: List of files to upload (up to 50 files)
        error_strategy: How to handle failures - "continue" (default) or "fail_all"
        use_case: Injected batch upload use case
        
    Returns:
        Dictionary with batch_id, total_documents, and status
        
    Example response:
        {
            "batch_id": "550e8400-e29b-41d4-a716-446655440000",
            "total_documents": 5,
            "status": "queued",
            "error_strategy": "continue"
        }
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    # Read all files
    file_data = []
    for file in files:
        if not file.filename:
            raise HTTPException(status_code=400, detail="All files must have filenames")
        
        file_bytes = await file.read()
        extension = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        
        file_data.append((
            file.filename,
            extension,
            file_bytes,
            file.content_type,
        ))

    # Execute batch upload
    batch = use_case.execute(file_data, error_strategy=error_strategy)

    return {
        "batch_id": batch.id,
        "total_documents": batch.total_documents,
        "status": batch.status,
        "error_strategy": batch.error_strategy,
        "created_at": batch.created_at.isoformat(),
    }


@router.get("/{batch_id}")
async def get_batch_details(
    batch_id: str,
    repository: BatchJobRepository = Depends(get_batch_repository),
) -> dict:
    """Get full batch status and all document jobs.
    
    This endpoint returns the complete state of a batch including
    all document jobs and their current status.
    
    Args:
        batch_id: Unique batch identifier
        repository: Injected batch repository
        
    Returns:
        Dictionary with complete batch details
        
    Example response:
        {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "status": "processing",
            "total_documents": 5,
            "completed_documents": 2,
            "failed_documents": 1,
            "progress_percentage": 60.0,
            "document_jobs": [...]
        }
    """
    batch = repository.get_batch(batch_id)
    
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")

    return {
        "id": batch.id,
        "created_at": batch.created_at.isoformat(),
        "status": batch.status,
        "total_documents": batch.total_documents,
        "completed_documents": batch.completed_documents,
        "failed_documents": batch.failed_documents,
        "progress_percentage": batch.progress_percentage,
        "error_strategy": batch.error_strategy,
        "started_at": batch.started_at.isoformat() if batch.started_at else None,
        "completed_at": batch.completed_at.isoformat() if batch.completed_at else None,
        "is_finished": batch.is_finished,
        "document_jobs": [
            {
                "document_id": job.document_id,
                "filename": job.filename,
                "status": job.status,
                "current_stage": job.current_stage,
                "completed_stages": job.completed_stages,
                "error_message": job.error_message,
                "run_id": job.run_id,
                "created_at": job.created_at.isoformat(),
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            }
            for job in batch.document_jobs.values()
        ],
    }


@router.get("/{batch_id}/stream")
async def batch_status_stream(
    batch_id: str,
    repository: BatchJobRepository = Depends(get_batch_repository),
) -> EventSourceResponse:
    """Server-Sent Events stream for real-time batch progress.
    
    This endpoint provides a real-time stream of batch processing events.
    Clients can use EventSource API to receive updates as documents progress
    through the pipeline.
    
    Event types:
        - batch_started: Batch processing has begun
        - document_stage_update: A document has progressed to a new stage
        - document_completed: A document has finished successfully
        - document_failed: A document has failed
        - batch_completed: All documents have finished
        - batch_update: General batch status update
        
    Args:
        batch_id: Unique batch identifier
        repository: Injected batch repository
        
    Returns:
        EventSourceResponse with SSE stream
    """
    batch = repository.get_batch(batch_id)
    
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")

    async def event_generator() -> AsyncGenerator[dict, None]:
        """Generate SSE events for batch progress."""
        last_status = None
        last_doc_statuses = {}
        
        # Send initial batch state
        yield {
            "event": "batch_started",
            "data": json.dumps({
                "batch_id": batch_id,
                "total_documents": batch.total_documents,
                "status": batch.status,
            }),
        }

        # Poll for updates until batch is finished
        while True:
            current_batch = repository.get_batch(batch_id)
            
            if not current_batch:
                yield {
                    "event": "error",
                    "data": json.dumps({"error": "Batch not found"}),
                }
                break

            # Check if batch status changed
            if current_batch.status != last_status:
                last_status = current_batch.status
                
                if current_batch.is_finished:
                    yield {
                        "event": "batch_completed",
                        "data": json.dumps({
                            "batch_id": batch_id,
                            "status": current_batch.status,
                            "completed_documents": current_batch.completed_documents,
                            "failed_documents": current_batch.failed_documents,
                            "total_documents": current_batch.total_documents,
                        }),
                    }
                    break
                else:
                    yield {
                        "event": "batch_update",
                        "data": json.dumps({
                            "batch_id": batch_id,
                            "status": current_batch.status,
                            "progress_percentage": current_batch.progress_percentage,
                        }),
                    }

            # Check for document job updates
            for doc_id, doc_job in current_batch.document_jobs.items():
                last_doc_status = last_doc_statuses.get(doc_id, {})
                
                # Check if stage changed
                if doc_job.current_stage != last_doc_status.get("current_stage"):
                    yield {
                        "event": "document_stage_update",
                        "data": json.dumps({
                            "batch_id": batch_id,
                            "document_id": doc_id,
                            "filename": doc_job.filename,
                            "stage": doc_job.current_stage,
                            "status": doc_job.status,
                            "completed_stages": doc_job.completed_stages,
                        }),
                    }

                # Check if document completed
                if doc_job.status == "completed" and last_doc_status.get("status") != "completed":
                    yield {
                        "event": "document_completed",
                        "data": json.dumps({
                            "batch_id": batch_id,
                            "document_id": doc_id,
                            "filename": doc_job.filename,
                        }),
                    }

                # Check if document failed
                if doc_job.status == "failed" and last_doc_status.get("status") != "failed":
                    yield {
                        "event": "document_failed",
                        "data": json.dumps({
                            "batch_id": batch_id,
                            "document_id": doc_id,
                            "filename": doc_job.filename,
                            "error": doc_job.error_message,
                        }),
                    }

                # Update last known status
                last_doc_statuses[doc_id] = {
                    "current_stage": doc_job.current_stage,
                    "status": doc_job.status,
                }

            # Wait before next poll
            await asyncio.sleep(0.5)

    return EventSourceResponse(event_generator())


@router.get("/")
async def list_batches(
    limit: int = 20,
    repository: BatchJobRepository = Depends(get_batch_repository),
) -> dict:
    """List recent batch jobs.
    
    Args:
        limit: Maximum number of batches to return (default 20)
        repository: Injected batch repository
        
    Returns:
        Dictionary with list of batch summaries
    """
    batches = repository.list_batches(limit=limit)
    
    return {
        "batches": [
            {
                "id": batch.id,
                "created_at": batch.created_at.isoformat(),
                "status": batch.status,
                "total_documents": batch.total_documents,
                "completed_documents": batch.completed_documents,
                "failed_documents": batch.failed_documents,
                "progress_percentage": batch.progress_percentage,
            }
            for batch in batches
        ],
        "total": len(batches),
    }


