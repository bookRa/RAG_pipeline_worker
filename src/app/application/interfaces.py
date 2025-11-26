from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Mapping, Protocol, Sequence, Any, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from ..parsing.schemas import CleanedPage, ParsedPage


class TaskScheduler(Protocol):
    """Port describing how background work should be scheduled."""

    def schedule(self, func: Callable[[], None]) -> None:
        """Schedule the provided callable for asynchronous execution."""


@runtime_checkable
class DocumentParser(Protocol):
    """Port for file-type specific document parsers."""

    supported_types: Sequence[str]

    def supports_type(self, file_type: str) -> bool:
        """Return True if the parser handles the provided file type."""

    def parse(self, file_bytes: bytes, filename: str) -> list[str]:
        """Parse raw bytes and return a list of page texts."""


class SummaryGenerator(Protocol):
    """Port for generating summaries (LLM, heuristics, etc.)."""

    def summarize(self, text: str) -> str:
        """Return a short summary of the provided text.
        
        Note: This is a generic method. Use specific methods below for structured summarization.
        """
    
    def summarize_document(
        self,
        filename: str,
        file_type: str,
        page_count: int,
        page_summaries: Sequence[tuple[int, str]],
    ) -> str:
        """Generate a comprehensive document-level summary from page summaries.
        
        Args:
            filename: Document filename
            file_type: Document file extension/type
            page_count: Total number of pages
            page_summaries: List of (page_number, summary) tuples
        
        Returns:
            A 3-4 sentence summary capturing document type, main topics, key entities, and scope.
        """
    
    def summarize_chunk(
        self,
        chunk_text: str,
        document_title: str,
        document_summary: str,
        page_summary: str | None,
        component_type: str | None,
    ) -> str:
        """Generate a chunk summary with hierarchical context.
        
        Args:
            chunk_text: The text content to summarize
            document_title: Name of the source document
            document_summary: Brief overview of the entire document
            page_summary: Summary of the page this chunk comes from
            component_type: Type of component (text, table, image)
        
        Returns:
            A 2-sentence summary explaining what the chunk contains and how it relates to the document.
        """


class ObservabilityRecorder(Protocol):
    """Port describing how domain events are emitted."""

    def record_event(
        self, 
        stage: str, 
        details: Mapping[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> None:
        """Emit a structured event for the given stage.
        
        Args:
            stage: Name of the pipeline stage
            details: Optional structured details about the event
            trace_id: Optional trace ID for linking events in observability systems
        """


class NullObservabilityRecorder(ObservabilityRecorder):
    """No-op recorder used by default in tests and as a fallback."""

    def record_event(
        self, 
        stage: str, 
        details: Mapping[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> None:  # noqa: D401
        """No-op implementation that does nothing."""
        return None


class ParsingLLM(Protocol):
    """LLM-driven parser that turns raw page data into structured content."""

    def parse_page(
        self,
        *,
        document_id: str,
        page_number: int,
        raw_text: str,
        pixmap_path: str | None = None,
    ) -> ParsedPage:
        """Return a structured representation of a page (paragraphs, tables, figures)."""


class CleaningLLM(Protocol):
    """LLM-driven cleaner that normalizes parsed content."""

    def clean_page(self, parsed_page: ParsedPage, pixmap_path: str | None = None) -> CleanedPage:
        """Return a cleaned version of the parsed page with normalized segments.
        
        Args:
            parsed_page: The parsed page to clean
            pixmap_path: Optional path to page image for vision-based cleaning context
        """


class EmbeddingGenerator(Protocol):
    """Port describing how text embeddings are produced."""

    @property
    def dimension(self) -> int:
        """Return the vector dimension for downstream consumers."""

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Generate embeddings for one or more text inputs."""


class VectorStoreAdapter(Protocol):
    """Port describing how chunk vectors are stored and retrieved."""

    def upsert_chunks(self, document_id: str, vectors: Sequence[Mapping[str, Any]]) -> None:
        """Persist vectors (with metadata) for a document."""

    def delete_document(self, document_id: str) -> None:
        """Remove all vectors associated with a document."""


class QueryEnginePort(Protocol):
    """Port describing how downstream systems can query stored chunks."""

    def query(self, prompt: str, *, top_k: int = 5) -> Mapping[str, Any]:
        """Execute a retrieval/query request and return structured results."""
