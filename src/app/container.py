from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from .config import settings
from .adapters.docx_parser import DocxParserAdapter
from .adapters.llm_client import LLMSummaryAdapter
from .adapters.pdf_parser import PdfParserAdapter
from .adapters.ppt_parser import PptParserAdapter
from .persistence.adapters.document_filesystem import FileSystemDocumentRepository
from .persistence.adapters.filesystem import FileSystemPipelineRunRepository
from .persistence.adapters.ingestion_filesystem import FileSystemIngestionRepository
from .observability.logger import LoggingObservabilityRecorder
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
        stage_latency = float(os.getenv("PIPELINE_STAGE_LATENCY", "0.05"))
        self.settings = settings
        base_dir = Path(__file__).resolve().parents[2]
        ingestion_storage_dir = Path(
            os.getenv("INGESTION_STORAGE_DIR", base_dir / "artifacts" / "ingestion")
        ).resolve()
        self.ingestion_repository = FileSystemIngestionRepository(ingestion_storage_dir)
        documents_dir = Path(os.getenv("DOCUMENT_STORAGE_DIR", base_dir / "artifacts" / "documents")).resolve()
        self.document_repository = FileSystemDocumentRepository(documents_dir)
        self.document_parsers = [
            PdfParserAdapter(),
            DocxParserAdapter(),
            PptParserAdapter(),
        ]
        self.summary_generator = LLMSummaryAdapter()

        self.observability = LoggingObservabilityRecorder()

        self.ingestion_service = IngestionService(
            latency=stage_latency,
            repository=self.ingestion_repository,
            observability=self.observability,
        )
        self.extraction_service = ExtractionService(
            latency=stage_latency,
            parsers=self.document_parsers,
            observability=self.observability,
        )
        self.cleaning_service = CleaningService(latency=stage_latency, observability=self.observability)
        self.chunking_service = ChunkingService(latency=stage_latency, observability=self.observability)
        self.enrichment_service = EnrichmentService(
            latency=stage_latency,
            summary_generator=self.summary_generator,
            observability=self.observability,
        )
        self.vector_service = VectorService(latency=stage_latency, observability=self.observability)

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
            observability=self.observability,
        )
        self.pipeline_run_manager = PipelineRunManager(
            self.run_repository,
            self.pipeline_runner,
            document_repository=self.document_repository,
        )


@lru_cache
def get_app_container() -> AppContainer:
    """Return a cached container instance so FastAPI dependencies share services."""

    return AppContainer()
