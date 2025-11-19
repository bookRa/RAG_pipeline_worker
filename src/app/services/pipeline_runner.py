from __future__ import annotations

from datetime import datetime
from time import perf_counter
from typing import Any, Callable, Iterable

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
        langfuse_handler: Any | None = None,
    ) -> None:
        self.ingestion = ingestion
        self.parsing = parsing
        self.cleaning = cleaning
        self.chunking = chunking
        self.enrichment = enrichment
        self.vectorization = vectorization
        self.observability = observability
        self.langfuse_handler = langfuse_handler

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
        
        # Create Langfuse trace for this pipeline run if handler is available
        langfuse_trace = None
        langfuse_trace_id = None
        if self.langfuse_handler and hasattr(self.langfuse_handler, 'langfuse'):
            try:
                langfuse_trace = self.langfuse_handler.langfuse.trace(
                    name="document_processing_pipeline",
                    input={
                        "document_id": document.id,
                        "filename": document.filename,
                    },
                    metadata={
                        "file_type": document.file_type,
                        "size_bytes": document.size_bytes,
                    },
                )
                langfuse_trace_id = langfuse_trace.id if hasattr(langfuse_trace, 'id') else None
                
                # Add trace ID to document metadata for linking
                if langfuse_trace_id and document.metadata:
                    document = document.model_copy(
                        update={"metadata": {**document.metadata, "langfuse_trace_id": langfuse_trace_id}}
                    )
            except Exception as exc:
                # Log but don't fail if Langfuse tracing fails
                import logging
                logger = logging.getLogger(__name__)
                logger.warning("Failed to create Langfuse trace: %s", exc)

        def register_stage(stage: PipelineStage) -> None:
            stage.completed_at = datetime.utcnow()
            stages.append(stage)
            if progress_callback:
                progress_callback(stage, document)

        def create_langfuse_span(stage_name: str, input_data: dict[str, Any] | None = None) -> Any:
            """Create a Langfuse span for a pipeline stage."""
            if langfuse_trace and hasattr(langfuse_trace, 'span'):
                try:
                    return langfuse_trace.span(
                        name=stage_name,
                        input=input_data or {},
                    )
                except Exception:
                    return None
            return None

        def end_langfuse_span(span: Any, output_data: dict[str, Any] | None = None) -> None:
            """End a Langfuse span."""
            if span and hasattr(span, 'end'):
                try:
                    span.end(output=output_data or {})
                except Exception:
                    pass

        stage_start = perf_counter()
        ingestion_span = create_langfuse_span("ingestion", {"filename": document.filename})
        document = self.ingestion.ingest(document, file_bytes=file_bytes)
        ingestion_duration = (perf_counter() - stage_start) * 1000
        end_langfuse_span(ingestion_span, {
            "status": document.status,
            "filename": document.filename,
            "file_type": document.file_type,
            "size_bytes": document.size_bytes,
        })
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
                duration_ms=ingestion_duration,
            )
        )

        stage_start = perf_counter()
        parsing_span = create_langfuse_span("parsing", {"page_count": len(document.pages)})
        document = self.parsing.parse(document, file_bytes=file_bytes)
        pixmap_metrics = document.metadata.get("pixmap_metrics") if document.metadata else None
        parsed_pages_meta = document.metadata.get("parsed_pages", {})
        
        # Build page details with components
        page_details = []
        for page in document.pages:
            page_data = {
                "page_number": page.page_number,
                "text_preview": page.text[:500],
            }
            
            # Add components if available
            parsed_page_data = parsed_pages_meta.get(str(page.page_number)) or parsed_pages_meta.get(page.page_number)
            if parsed_page_data:
                components = parsed_page_data.get("components", [])
                # Sort components by order
                sorted_components = sorted(components, key=lambda c: c.get("order", 0))
                page_data["components"] = sorted_components
                page_data["component_count"] = len(sorted_components)
                # Count by type
                page_data["component_summary"] = {
                    "text": len([c for c in sorted_components if c.get("type") == "text"]),
                    "image": len([c for c in sorted_components if c.get("type") == "image"]),
                    "table": len([c for c in sorted_components if c.get("type") == "table"]),
                }
            
            page_details.append(page_data)
        
        parsing_duration = (perf_counter() - stage_start) * 1000
        end_langfuse_span(parsing_span, {
            "page_count": len(document.pages),
            "pixmap_metrics": pixmap_metrics or {},
        })
        register_stage(
            PipelineStage(
                name="parsing",
                title="Parsing",
                details={
                    "page_count": len(document.pages),
                    "pages": page_details,
                    "pixmap_metrics": pixmap_metrics or {},
                },
                duration_ms=parsing_duration,
            )
        )

        stage_start = perf_counter()
        cleaning_span = create_langfuse_span("cleaning")
        document = self.cleaning.clean(document)
        cleaning_report = document.metadata.get("cleaning_report", [])
        cleaning_duration = (perf_counter() - stage_start) * 1000
        end_langfuse_span(cleaning_span, {
            "pages_cleaned": len(document.pages),
            "profile": self.cleaning.profile,
        })
        register_stage(
            PipelineStage(
                name="cleaning",
                title="Cleaning",
                details={
                    "profile": self.cleaning.profile,
                    "pages": cleaning_report,
                },
                duration_ms=cleaning_duration,
            )
        )

        stage_start = perf_counter()
        chunking_span = create_langfuse_span("chunking")
        document = self.chunking.chunk(document)
        chunk_count = sum(len(page.chunks) for page in document.pages)
        chunking_duration = (perf_counter() - stage_start) * 1000
        end_langfuse_span(chunking_span, {"chunk_count": chunk_count})
        register_stage(
            PipelineStage(
                name="chunking",
                title="Chunking",
                details={
                    "chunk_count": chunk_count,
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
                duration_ms=chunking_duration,
            )
        )

        stage_start = perf_counter()
        enrichment_span = create_langfuse_span("enrichment")
        document = self.enrichment.enrich(document)
        enrichment_duration = (perf_counter() - stage_start) * 1000
        end_langfuse_span(enrichment_span, {
            "document_summary": document.summary or "",
            "chunk_count": sum(len(page.chunks) for page in document.pages),
        })
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
                duration_ms=enrichment_duration,
            )
        )

        stage_start = perf_counter()
        vectorization_span = create_langfuse_span("vectorization")
        document = self.vectorization.vectorize(document)
        vector_count = sum(len(page.chunks) for page in document.pages)
        vectorization_duration = (perf_counter() - stage_start) * 1000
        end_langfuse_span(vectorization_span, {
            "vector_dimension": self.vectorization.dimension,
            "vector_count": vector_count,
        })
        register_stage(
            PipelineStage(
                name="vectorization",
                title="Vectorization",
                details={
                    "vector_dimension": self.vectorization.dimension,
                    "vector_count": vector_count,
                    "sample_vectors": document.metadata.get("vector_samples", []),
                },
                duration_ms=vectorization_duration,
            )
        )

        # Update Langfuse trace with final status
        if langfuse_trace and hasattr(langfuse_trace, 'update'):
            try:
                langfuse_trace.update(output={
                    "final_status": document.status,
                    "stages": [stage.name for stage in stages],
                })
            except Exception:
                pass

        # Extract trace_id from document metadata if available
        trace_id = None
        if document.metadata and "langfuse_trace_id" in document.metadata:
            trace_id = document.metadata["langfuse_trace_id"]

        self.observability.record_event(
            stage="pipeline_complete",
            details={"document_id": document.id, "stages": [stage.name for stage in stages]},
            trace_id=trace_id,
        )
        return PipelineResult(document=document, stages=stages)
