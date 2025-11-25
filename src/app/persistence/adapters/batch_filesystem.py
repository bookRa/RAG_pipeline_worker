"""Filesystem adapter for batch job persistence."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from ...domain.batch_models import BatchJob, DocumentJob
from ..ports import BatchJobRepository


class FileSystemBatchJobRepository(BatchJobRepository):
    """Stores batch jobs as JSON artifacts on disk.
    
    Storage structure:
        artifacts/batches/{batch_id}/
            batch.json          - Batch metadata and aggregate status
            documents/
                {doc_id}.json   - Individual document job details
    """

    def __init__(self, base_dir: Path | str) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def create_batch(self, batch: BatchJob) -> None:
        """Persist a new batch job with all its document jobs."""
        batch_dir = self._batch_dir(batch.id)
        batch_dir.mkdir(parents=True, exist_ok=True)
        docs_dir = self._documents_dir(batch.id)
        docs_dir.mkdir(parents=True, exist_ok=True)
        
        # Write batch metadata
        batch_data = self._serialize_batch(batch)
        self._write_json(batch_dir / "batch.json", batch_data)
        
        # Write individual document jobs
        for doc_job in batch.document_jobs.values():
            self._write_document_job(batch.id, doc_job)

    def get_batch(self, batch_id: str) -> BatchJob | None:
        """Fetch a batch job by id, including all document jobs."""
        batch_dir = self._batch_dir(batch_id)
        batch_path = batch_dir / "batch.json"
        
        if not batch_path.exists():
            return None
        
        batch_data = self._read_json(batch_path)
        if not batch_data:
            return None
        
        # Load all document jobs
        document_jobs = self._load_document_jobs(batch_id)
        
        return self._deserialize_batch(batch_data, document_jobs)

    def update_batch(self, batch: BatchJob) -> None:
        """Update an existing batch job."""
        batch_dir = self._batch_dir(batch.id)
        if not batch_dir.exists():
            # Batch doesn't exist yet, create it
            self.create_batch(batch)
            return
        
        # Update batch metadata
        batch_data = self._serialize_batch(batch)
        self._write_json(batch_dir / "batch.json", batch_data)
        
        # Update all document jobs
        for doc_job in batch.document_jobs.values():
            self._write_document_job(batch.id, doc_job)

    def update_document_job(self, batch_id: str, doc_job: DocumentJob) -> None:
        """Update a specific document job within a batch."""
        self._write_document_job(batch_id, doc_job)
        
        # Also update the batch's aggregate status
        batch = self.get_batch(batch_id)
        if batch:
            batch.document_jobs[doc_job.document_id] = doc_job
            batch.update_status()
            # Write updated batch metadata
            batch_data = self._serialize_batch(batch)
            self._write_json(self._batch_dir(batch_id) / "batch.json", batch_data)

    def list_batches(self, limit: int = 20) -> list[BatchJob]:
        """Return the most recent batch jobs, sorted by creation time."""
        batches: list[BatchJob] = []
        
        for batch_dir in sorted(
            self.base_dir.iterdir(),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        ):
            if not batch_dir.is_dir():
                continue
            
            batch = self.get_batch(batch_dir.name)
            if batch:
                batches.append(batch)
            
            if len(batches) >= limit:
                break
        
        return batches

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------
    def _serialize_batch(self, batch: BatchJob) -> dict[str, Any]:
        """Convert BatchJob to JSON-serializable dict."""
        data = {
            "id": batch.id,
            "created_at": batch.created_at.isoformat(),
            "status": batch.status,
            "total_documents": batch.total_documents,
            "completed_documents": batch.completed_documents,
            "failed_documents": batch.failed_documents,
            "error_strategy": batch.error_strategy,
            "started_at": batch.started_at.isoformat() if batch.started_at else None,
            "completed_at": batch.completed_at.isoformat() if batch.completed_at else None,
            "document_job_ids": list(batch.document_jobs.keys()),  # Just store IDs, not full objects
        }
        return data

    def _deserialize_batch(
        self,
        data: dict[str, Any],
        document_jobs: dict[str, DocumentJob],
    ) -> BatchJob:
        """Convert JSON dict to BatchJob instance."""
        return BatchJob(
            id=data["id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            status=data.get("status", "queued"),
            total_documents=data.get("total_documents", 0),
            completed_documents=data.get("completed_documents", 0),
            failed_documents=data.get("failed_documents", 0),
            document_jobs=document_jobs,
            error_strategy=data.get("error_strategy", "continue"),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
        )

    def _serialize_document_job(self, doc_job: DocumentJob) -> dict[str, Any]:
        """Convert DocumentJob to JSON-serializable dict."""
        return {
            "document_id": doc_job.document_id,
            "filename": doc_job.filename,
            "status": doc_job.status,
            "current_stage": doc_job.current_stage,
            "error_message": doc_job.error_message,
            "run_id": doc_job.run_id,
            "completed_stages": doc_job.completed_stages,
            "created_at": doc_job.created_at.isoformat(),
            "started_at": doc_job.started_at.isoformat() if doc_job.started_at else None,
            "completed_at": doc_job.completed_at.isoformat() if doc_job.completed_at else None,
        }

    def _deserialize_document_job(self, data: dict[str, Any]) -> DocumentJob:
        """Convert JSON dict to DocumentJob instance."""
        return DocumentJob(
            document_id=data["document_id"],
            filename=data["filename"],
            status=data.get("status", "queued"),
            current_stage=data.get("current_stage"),
            error_message=data.get("error_message"),
            run_id=data.get("run_id"),
            completed_stages=data.get("completed_stages", []),
            created_at=datetime.fromisoformat(data["created_at"]),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
        )

    # ------------------------------------------------------------------
    # IO utilities
    # ------------------------------------------------------------------
    def _batch_dir(self, batch_id: str) -> Path:
        """Get the directory for a specific batch."""
        return self.base_dir / batch_id

    def _documents_dir(self, batch_id: str) -> Path:
        """Get the documents subdirectory for a specific batch."""
        docs_dir = self._batch_dir(batch_id) / "documents"
        docs_dir.mkdir(parents=True, exist_ok=True)
        return docs_dir

    def _write_document_job(self, batch_id: str, doc_job: DocumentJob) -> None:
        """Write a document job to disk."""
        doc_path = self._documents_dir(batch_id) / f"{doc_job.document_id}.json"
        doc_data = self._serialize_document_job(doc_job)
        self._write_json(doc_path, doc_data)

    def _load_document_jobs(self, batch_id: str) -> dict[str, DocumentJob]:
        """Load all document jobs for a batch."""
        docs_dir = self._documents_dir(batch_id)
        document_jobs: dict[str, DocumentJob] = {}
        
        if not docs_dir.exists():
            return document_jobs
        
        for doc_file in docs_dir.glob("*.json"):
            doc_data = self._read_json(doc_file)
            if doc_data:
                doc_job = self._deserialize_document_job(doc_data)
                document_jobs[doc_job.document_id] = doc_job
        
        return document_jobs

    def _write_json(self, path: Path, payload: Any) -> None:
        """Write JSON to a file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        """Read JSON from a file."""
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)


