from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ...domain.models import Document
from ...domain.run_models import PipelineResult, PipelineRunRecord, PipelineStage
from ..ports import PipelineRunRepository


class FileSystemPipelineRunRepository(PipelineRunRepository):
    """Stores pipeline runs as JSON artifacts on disk."""

    def __init__(self, base_dir: Path | str) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def start_run(self, run: PipelineRunRecord) -> None:
        run_dir = self._run_dir(run.id)
        (run_dir / "stages").mkdir(parents=True, exist_ok=True)
        metadata = self._serialize_run_metadata(run)
        self._write_json(run_dir / "run.json", metadata)
        if run.document:
            self._write_document(run.id, run.document)

    def update_stage(self, run_id: str, stage: PipelineStage, document: Document | None = None) -> None:
        run_dir = self._run_dir(run_id)
        if not run_dir.exists():
            return
        metadata = self._read_json(run_dir / "run.json")
        if not metadata:
            return
        stage_order = metadata.setdefault("stage_order", [])
        if stage.name not in stage_order:
            stage_order.append(stage.name)
        metadata["updated_at"] = datetime.utcnow().isoformat()
        self._write_json(run_dir / "run.json", metadata)
        self._write_stage(run_id, stage)
        if document:
            self._write_document(run_id, document)

    def complete_run(self, run_id: str, result: PipelineResult) -> None:
        run_dir = self._run_dir(run_id)
        if not run_dir.exists():
            return
        metadata = self._read_json(run_dir / "run.json")
        if not metadata:
            return
        metadata["status"] = "completed"
        metadata["updated_at"] = datetime.utcnow().isoformat()
        metadata["completed_at"] = metadata["updated_at"]
        self._write_json(run_dir / "run.json", metadata)
        self._write_document(run_id, result.document)
        for stage in result.stages:
            self._write_stage(run_id, stage)

    def fail_run(self, run_id: str, error_message: str) -> None:
        run_dir = self._run_dir(run_id)
        if not run_dir.exists():
            return
        metadata = self._read_json(run_dir / "run.json")
        if not metadata:
            return
        metadata["status"] = "failed"
        metadata["error_message"] = error_message
        metadata["updated_at"] = datetime.utcnow().isoformat()
        self._write_json(run_dir / "run.json", metadata)

    def get_run(self, run_id: str) -> PipelineRunRecord | None:
        run_dir = self._run_dir(run_id)
        run_meta = self._read_json(run_dir / "run.json")
        if not run_meta:
            return None
        document = self._read_document(run_id)
        stage_map: dict[str, PipelineStage] = {}
        for stage_name in run_meta.get("stage_order", []):
            stage = self._read_stage(run_id, stage_name)
            if stage:
                stage_map[stage_name] = stage
        record = self._deserialize_run_metadata(run_meta, document, stage_map)
        return record

    def list_runs(self, limit: int = 10) -> list[PipelineRunRecord]:
        records: list[PipelineRunRecord] = []
        for run_dir in sorted(
            self.base_dir.iterdir(),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        ):
            if not run_dir.is_dir():
                continue
            run = self.get_run(run_dir.name)
            if run:
                records.append(run)
            if len(records) >= limit:
                break
        return records

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------
    def _serialize_run_metadata(self, run: PipelineRunRecord) -> dict[str, Any]:
        return {
            "id": run.id,
            "created_at": run.created_at.isoformat(),
            "filename": run.filename,
            "content_type": run.content_type,
            "file_path": run.file_path,
            "status": run.status,
            "error_message": run.error_message,
            "stage_order": list(run.stage_map.keys()),
            "updated_at": datetime.utcnow().isoformat(),
        }

    def _deserialize_run_metadata(
        self,
        data: dict[str, Any],
        document: Document | None,
        stage_map: dict[str, PipelineStage],
    ) -> PipelineRunRecord:
        record = PipelineRunRecord(
            id=data["id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            filename=data.get("filename", ""),
            content_type=data.get("content_type"),
            file_path=data.get("file_path"),
            document=document,
            status=data.get("status", "running"),
            error_message=data.get("error_message"),
        )
        for stage in stage_map.values():
            record.update_stage(stage)
        if document and stage_map:
            record.result = PipelineResult(document=document, stages=list(stage_map.values()))
        return record

    def _serialize_stage(self, stage: PipelineStage) -> dict[str, Any]:
        return {
            "name": stage.name,
            "title": stage.title,
            "details": stage.details,
            "duration_ms": stage.duration_ms,
            "completed_at": stage.completed_at.isoformat() if stage.completed_at else None,
        }

    def _deserialize_stage(self, data: dict[str, Any]) -> PipelineStage:
        return PipelineStage(
            name=data["name"],
            title=data.get("title", data["name"].title()),
            details=data.get("details", {}),
            duration_ms=data.get("duration_ms"),
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
        )

    # ------------------------------------------------------------------
    # IO utilities
    # ------------------------------------------------------------------
    def _run_dir(self, run_id: str) -> Path:
        return self.base_dir / run_id

    def _stages_dir(self, run_id: str) -> Path:
        stages_dir = self._run_dir(run_id) / "stages"
        stages_dir.mkdir(parents=True, exist_ok=True)
        return stages_dir

    def _write_document(self, run_id: str, document: Document) -> None:
        doc_path = self._run_dir(run_id) / "document.json"
        self._write_json(doc_path, document.model_dump(mode="json"))

    def _read_document(self, run_id: str) -> Document | None:
        doc_path = self._run_dir(run_id) / "document.json"
        if not doc_path.exists():
            return None
        data = self._read_json(doc_path)
        if not data:
            return None
        return Document.model_validate(data)

    def _write_stage(self, run_id: str, stage: PipelineStage) -> None:
        stage_path = self._stages_dir(run_id) / f"{stage.name}.json"
        self._write_json(stage_path, self._serialize_stage(stage))

    def _read_stage(self, run_id: str, stage_name: str) -> PipelineStage | None:
        stage_path = self._stages_dir(run_id) / f"{stage_name}.json"
        if not stage_path.exists():
            return None
        data = self._read_json(stage_path)
        if not data:
            return None
        return self._deserialize_stage(data)

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
