from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from .config import settings
from .persistence.adapters.filesystem import FileSystemPipelineRunRepository
from .services.chunking_service import ChunkingService
from .services.cleaning_service import CleaningService
from .services.enrichment_service import EnrichmentService
from .services.extraction_service import ExtractionService
from .services.ingestion_service import IngestionService
from .services.pipeline_runner import PipelineRunner
from .services.run_manager import PipelineRunManager
from .services.vector_service import VectorService


class AppContainer:
    """Application composition root wiring services, repositories, and adapters."""

    def __init__(self) -> None:
        stage_latency = float(os.getenv("PIPELINE_STAGE_LATENCY", "2.05"))
        self.settings = settings
        self.ingestion_service = IngestionService(latency=stage_latency)
        self.extraction_service = ExtractionService(latency=stage_latency)
        self.cleaning_service = CleaningService(latency=stage_latency)
        self.chunking_service = ChunkingService(latency=stage_latency)
        self.enrichment_service = EnrichmentService(latency=stage_latency)
        self.vector_service = VectorService(latency=stage_latency)

        base_dir = Path(__file__).resolve().parents[2]
        artifacts_dir = Path(
            os.getenv("RUN_ARTIFACTS_DIR", base_dir / "artifacts" / "runs")
        ).resolve()
        self.run_repository = FileSystemPipelineRunRepository(artifacts_dir)

        self.pipeline_runner = PipelineRunner(
            ingestion=self.ingestion_service,
            extraction=self.extraction_service,
            cleaning=self.cleaning_service,
            chunking=self.chunking_service,
            enrichment=self.enrichment_service,
            vectorization=self.vector_service,
        )
        self.pipeline_run_manager = PipelineRunManager(
            self.run_repository, self.pipeline_runner
        )


@lru_cache
def get_app_container() -> AppContainer:
    """Return a cached container instance so FastAPI dependencies share services."""

    return AppContainer()
