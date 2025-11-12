from __future__ import annotations

from datetime import datetime
from time import perf_counter
from typing import Callable, Iterable

from ..application.interfaces import ObservabilityRecorder
from ..domain.models import Document
from ..domain.run_models import PipelineResult, PipelineStage
from .chunking_service import ChunkingService
from .cleaning_service import CleaningService
from .enrichment_service import EnrichmentService
from .parsing_service import ParsingService
from .ingestion_service import IngestionService
from .vector_service import VectorService


class PipelineRunner:
    """Co-ordinates the ingestion -> parsing -> chunking -> enrichment flow."""

    def __init__(
        self,
        ingestion: IngestionService,
        parsing: ParsingService,
        cleaning: CleaningService,
        chunking: ChunkingService,
        enrichment: EnrichmentService,
        vectorization: VectorService,
        observability: ObservabilityRecorder,
    ) -> None:
        self.ingestion = ingestion
        self.parsing = parsing
        self.cleaning = cleaning
        self.chunking = chunking
        self.enrichment = enrichment
        self.vectorization = vectorization
        self.observability = observability

    STAGE_SEQUENCE: Iterable[tuple[str, str]] = (
        ("ingestion", "Ingestion"),
        ("parsing", "Parsing"),
        ("cleaning", "Cleaning"),
        ("chunking", "Chunking"),
        ("enrichment", "Enrichment"),
        ("vectorization", "Vectorization"),
    )

    def run(
        self,
        document: Document,
        *,
        file_bytes: bytes | None = None,
        progress_callback: Callable[[PipelineStage, Document], None] | None = None,
    ) -> PipelineResult:
        stages: list[PipelineStage] = []

        def register_stage(stage: PipelineStage) -> None:
            stage.completed_at = datetime.utcnow()
            stages.append(stage)
            if progress_callback:
                progress_callback(stage, document)

        stage_start = perf_counter()
        document = self.ingestion.ingest(document, file_bytes=file_bytes)
        register_stage(
            PipelineStage(
                name="ingestion",
                title="Ingestion",
                details={
                    "status": document.status,
                    "filename": document.filename,
                    "file_type": document.file_type,
                    "size_bytes": document.size_bytes,
                },
                duration_ms=(perf_counter() - stage_start) * 1000,
            )
        )

        stage_start = perf_counter()
        document = self.parsing.parse(document, file_bytes=file_bytes)
        pixmap_metrics = document.metadata.get("pixmap_metrics") if document.metadata else None
        register_stage(
            PipelineStage(
                name="parsing",
                title="Parsing",
                details={
                    "page_count": len(document.pages),
                    "pages": [
                        {
                            "page_number": page.page_number,
                            "text_preview": page.text[:500],
                        }
                        for page in document.pages
                    ],
                    "pixmap_metrics": pixmap_metrics or {},
                },
                duration_ms=(perf_counter() - stage_start) * 1000,
            )
        )

        stage_start = perf_counter()
        document = self.cleaning.clean(document)
        cleaning_report = document.metadata.get("cleaning_report", [])
        register_stage(
            PipelineStage(
                name="cleaning",
                title="Cleaning",
                details={
                    "profile": self.cleaning.profile,
                    "pages": cleaning_report,
                },
                duration_ms=(perf_counter() - stage_start) * 1000,
            )
        )

        stage_start = perf_counter()
        document = self.chunking.chunk(document)
        register_stage(
            PipelineStage(
                name="chunking",
                title="Chunking",
                details={
                    "chunk_count": sum(len(page.chunks) for page in document.pages),
                    "pages": [
                        {
                            "page_number": page.page_number,
                            "chunk_count": len(page.chunks),
                            "chunks": [
                                {
                                    "chunk_id": chunk.id,
                                    "offset": (chunk.start_offset, chunk.end_offset),
                                    "text_preview": chunk.text[:200],
                                    "metadata": chunk.metadata.model_dump()
                                    if chunk.metadata
                                    else {},
                                }
                                for chunk in page.chunks
                            ],
                        }
                        for page in document.pages
                    ],
                },
                duration_ms=(perf_counter() - stage_start) * 1000,
            )
        )

        stage_start = perf_counter()
        document = self.enrichment.enrich(document)
        register_stage(
            PipelineStage(
                name="enrichment",
                title="Enrichment",
                details={
                    "document_summary": document.summary or "",
                    "chunk_summaries": [
                        {
                            "chunk_id": chunk.id,
                            "summary": (chunk.metadata.summary if chunk.metadata else "")
                            or "",
                        }
                        for page in document.pages
                        for chunk in page.chunks
                    ],
                },
                duration_ms=(perf_counter() - stage_start) * 1000,
            )
        )

        stage_start = perf_counter()
        document = self.vectorization.vectorize(document)
        register_stage(
            PipelineStage(
                name="vectorization",
                title="Vectorization",
                details={
                    "vector_dimension": self.vectorization.dimension,
                    "vector_count": sum(len(page.chunks) for page in document.pages),
                    "sample_vectors": document.metadata.get("vector_samples", []),
                },
                duration_ms=(perf_counter() - stage_start) * 1000,
            )
        )

        self.observability.record_event(
            stage="pipeline_complete",
            details={"document_id": document.id, "stages": [stage.name for stage in stages]},
        )
        return PipelineResult(document=document, stages=stages)
