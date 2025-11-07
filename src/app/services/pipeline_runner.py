from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..domain.models import Document
from ..observability.logger import log_event
from .chunking_service import ChunkingService
from .cleaning_service import CleaningService
from .enrichment_service import EnrichmentService
from .extraction_service import ExtractionService
from .ingestion_service import IngestionService
from .vector_service import VectorService


@dataclass
class PipelineStage:
    name: str
    title: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineResult:
    document: Document
    stages: list[PipelineStage]

    def stage(self, name: str) -> PipelineStage | None:
        for stage in self.stages:
            if stage.name == name:
                return stage
        return None


class PipelineRunner:
    """Co-ordinates the ingestion -> extraction -> chunking -> enrichment flow."""

    def __init__(
        self,
        ingestion: IngestionService,
        extraction: ExtractionService,
        cleaning: CleaningService,
        chunking: ChunkingService,
        enrichment: EnrichmentService,
        vectorization: VectorService,
    ) -> None:
        self.ingestion = ingestion
        self.extraction = extraction
        self.cleaning = cleaning
        self.chunking = chunking
        self.enrichment = enrichment
        self.vectorization = vectorization

    def run(self, document: Document) -> PipelineResult:
        stages: list[PipelineStage] = []

        document = self.ingestion.ingest(document)
        stages.append(
            PipelineStage(
                name="ingestion",
                title="Ingestion",
                details={
                    "status": document.status,
                    "filename": document.filename,
                    "file_type": document.file_type,
                    "size_bytes": document.size_bytes,
                },
            )
        )

        document = self.extraction.extract(document)
        stages.append(
            PipelineStage(
                name="extraction",
                title="Extraction",
                details={
                    "page_count": len(document.pages),
                    "pages": [
                        {
                            "page_number": page.page_number,
                            "text_preview": page.text[:500],
                        }
                        for page in document.pages
                    ],
                },
            )
        )

        document = self.cleaning.clean(document)
        cleaning_report = document.metadata.get("cleaning_report", [])
        stages.append(
            PipelineStage(
                name="cleaning",
                title="Cleaning",
                details={
                    "profile": self.cleaning.profile,
                    "pages": cleaning_report,
                },
            )
        )

        document = self.chunking.chunk(document)
        stages.append(
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
            )
        )

        document = self.enrichment.enrich(document)
        stages.append(
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
            )
        )

        document = self.vectorization.vectorize(document)
        stages.append(
            PipelineStage(
                name="vectorization",
                title="Vectorization",
                details={
                    "vector_dimension": self.vectorization.dimension,
                    "vector_count": sum(len(page.chunks) for page in document.pages),
                    "sample_vectors": document.metadata.get("vector_samples", []),
                },
            )
        )

        log_event(
            stage="pipeline_complete",
            details={"document_id": document.id, "stages": [stage.name for stage in stages]},
        )
        return PipelineResult(document=document, stages=stages)
