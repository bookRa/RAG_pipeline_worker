from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .models import Document


@dataclass
class PipelineStage:
    name: str
    title: str
    details: dict[str, Any] = field(default_factory=dict)
    duration_ms: float | None = None
    completed_at: datetime | None = None


@dataclass
class PipelineResult:
    document: Document
    stages: list[PipelineStage]

    def stage(self, name: str) -> PipelineStage | None:
        for stage in self.stages:
            if stage.name == name:
                return stage
        return None


@dataclass
class PipelineRunRecord:
    id: str
    created_at: datetime
    filename: str
    content_type: str | None
    file_path: str | None
    document: Document | None = None
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
        if self.document is None:
            return 0
        return len(self.document.pages)
