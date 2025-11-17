from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class Metadata(BaseModel):
    """
    Metadata describing additional context for a chunk.
    
    This model captures enrichment data that helps with retrieval, filtering, and
    understanding the chunk's content. The `extra` field provides extensibility
    for service-specific metadata (e.g., cleaning operations, vector embeddings).
    
    Attributes:
        id: Unique identifier for this metadata record
        document_id: Reference to the parent document
        page_number: Page number where the chunk originates (may be extended for multi-page chunks)
        chunk_id: Reference to the chunk this metadata describes
        start_offset: Character offset in the raw page text where chunk starts
        end_offset: Character offset in the raw page text where chunk ends
        title: Optional human-readable title for the chunk
        summary: Optional summary or abstract of the chunk content
        keywords: List of keywords extracted from the chunk
        
        # Component Context (for Contextual Retrieval)
        component_id: Links chunk to source component in parsed page
        component_type: Type of component ("text", "image", "table")
        component_order: Order of component in page layout
        component_description: For images - the visual description
        component_summary: For tables - the table summary
        
        # Hierarchical Context (for Hierarchical RAG)
        document_title: Title/filename of the parent document
        document_summary: High-level summary of entire document
        page_summary: Summary of the page this chunk comes from
        section_heading: Heading of the section this chunk belongs to
        
        extra: Dictionary for extensible metadata (e.g., cleaning info, vector data)
    
    Cleaning Metadata Structure (stored in extra["cleaning"]):
        {
            "segment_id": chunk.id,  # Links metadata to chunk
            "cleaned_tokens_count": int,  # Token count after cleaning
            "diff_hash": str,  # Hash of "raw::cleaned" for change tracking
            "cleaning_ops": list[str],  # Operations applied (e.g., ["whitespace", "case_norm"])
            "needs_review": bool,  # Flag indicating manual review may be needed
            "profile": str  # Cleaning profile used (e.g., "default", "aggressive")
        }
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    document_id: str
    page_number: int
    chunk_id: str
    start_offset: int
    end_offset: int
    title: Optional[str] = None
    summary: Optional[str] = None
    keywords: list[str] = Field(default_factory=list)
    
    # Component context for contextual retrieval
    component_id: Optional[str] = Field(default=None, description="Links to parsed component ID")
    component_type: Optional[str] = Field(default=None, description="Component type: text, image, or table")
    component_order: Optional[int] = Field(default=None, description="Order in page layout")
    component_description: Optional[str] = Field(default=None, description="For images: visual description")
    component_summary: Optional[str] = Field(default=None, description="For tables: table summary")
    
    # Hierarchical context for hierarchical RAG
    document_title: Optional[str] = Field(default=None, description="Document filename/title")
    document_summary: Optional[str] = Field(default=None, description="Document-level summary")
    page_summary: Optional[str] = Field(default=None, description="Page-level summary")
    section_heading: Optional[str] = Field(default=None, description="Preceding section heading")
    
    extra: dict[str, Any] = Field(default_factory=dict)


class Chunk(BaseModel):
    """
    Represents a chunk of text derived from a document page.
    
    A chunk is a contiguous segment of text extracted from a document for processing,
    retrieval, and indexing. This model preserves both raw and cleaned versions of
    the text to support different use cases (e.g., exact source navigation vs. normalized search).
    
    Raw vs Cleaned vs Contextualized Text:
        - `text`: Always contains the raw, immutable text slice from the source document.
                This is the original parsing output, preserved exactly as parsed.
                 Offsets (start_offset, end_offset) reference positions in this raw text.
                 This enables precise document navigation and source citation.
        
        - `cleaned_text`: Optional normalized version of the text after cleaning operations
                          (whitespace normalization, case handling, etc.). This is a parallel
                          slice that corresponds to the same logical segment as `text`, but
                          may differ in length or content due to normalization.
                          Used for generation and display.
        
        - `contextualized_text`: Optional version with document/page/section context prepended.
                                 Format: "[Document: X | Page: Y | Section: Z | Type: T]\n\nclean_text"
                                 Used specifically for embedding to improve contextual retrieval.
                                 Follows Anthropic's contextual retrieval pattern.
    
    Future Extensibility for Semantic Chunking:
        Currently, chunks are assumed to come from a single page (page_number is a single int).
        Future semantic chunking may span multiple pages. When that is implemented, consider:
        - Adding `page_ranges: list[tuple[int, int, int]]` where each tuple is (page_num, start, end)
        - Or extending `page_number` to support page ranges
        - Ensuring offsets remain consistent with raw text positions for navigation
    
    Attributes:
        id: Unique identifier for this chunk
        document_id: Reference to the parent document
        page_number: Page number where chunk originates (single page for now, extensible for multi-page)
        text: Raw text slice from source document (immutable, preserves exact parsing output)
        start_offset: Character offset in raw page text where chunk starts (for navigation)
        end_offset: Character offset in raw page text where chunk ends (for navigation)
        cleaned_text: Optional cleaned/normalized version of the text (for generation)
        contextualized_text: Optional context-enriched text (for embedding)
        metadata: Optional enrichment metadata (keywords, summary, cleaning info, etc.)
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    document_id: str
    page_number: int
    text: str
    start_offset: int
    end_offset: int
    cleaned_text: Optional[str] = None
    contextualized_text: Optional[str] = Field(
        default=None,
        description="Context-enriched text for embedding (includes document/page/section context prefix)",
    )
    metadata: Optional[Metadata] = None


class Page(BaseModel):
    """
    A single page from a document, containing zero or more chunks.
    
    A page represents one logical page of extracted content. It preserves both
    raw and cleaned versions of the page text, which are then sliced into chunks
    during the chunking stage.
    
    Raw vs Cleaned Text:
        - `text`: Raw, immutable text parsed from the document (preserves exact parsing output)
        - `cleaned_text`: Optional normalized version after cleaning operations (whitespace, case, etc.)
    
    The cleaning service populates `cleaned_text` if cleaning has run. The chunking service
    then creates chunks by slicing from `text` (for raw chunks) and `cleaned_text` (for cleaned chunks).
    
    Attributes:
        id: Unique identifier for this page
        document_id: Reference to the parent document
        page_number: Sequential page number (1-indexed)
        text: Raw extracted text from this page (immutable source)
        cleaned_text: Optional cleaned/normalized version of the page text
        chunks: List of chunks derived from this page
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    document_id: str
    page_number: int
    text: str
    cleaned_text: Optional[str] = None
    chunks: list[Chunk] = Field(default_factory=list)


class Document(BaseModel):
    """Top-level representation of an uploaded document."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    filename: str
    file_type: Literal["pdf", "docx", "ppt", "pptx"]
    size_bytes: int = 0
    status: str = "created"
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    summary: Optional[str] = None
    pages: list[Page] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def add_page(self, page: Page) -> Document:
        """Return a new document with the page added, overwriting document_id if necessary."""

        normalized_page = page.model_copy(update={"document_id": self.id})
        # Ensure page numbers are unique; replace page if it already exists
        existing_index = next((i for i, p in enumerate(self.pages) if p.page_number == normalized_page.page_number), None)
        
        if existing_index is not None:
            updated_pages = self.pages.copy()
            updated_pages[existing_index] = normalized_page
        else:
            updated_pages = [*self.pages, normalized_page]
        
        return self.model_copy(update={"pages": updated_pages})
    
    def replace_page(self, page_number: int, new_page: Page) -> Document:
        """Return a new document with the specified page replaced."""
        updated_pages = [
            new_page if p.page_number == page_number else p
            for p in self.pages
        ]
        return self.model_copy(update={"pages": updated_pages})

    def add_chunk(self, page_number: int, chunk: Chunk) -> Document:
        """Return a new document with the chunk added to the appropriate page, creating the page if needed."""

        normalized_chunk = chunk.model_copy(
            update={
                "document_id": self.id,
                "page_number": page_number,
                "metadata": None if chunk.metadata is None else chunk.metadata.model_copy(
                    update={
                        "document_id": self.id,
                        "page_number": page_number,
                        "chunk_id": chunk.id,
                    }
                ),
            }
        )

        # Find or create the page
        page_index = next((i for i, p in enumerate(self.pages) if p.page_number == page_number), None)
        
        if page_index is not None:
            # Update existing page with new chunk
            existing_page = self.pages[page_index]
            updated_chunks = [*existing_page.chunks, normalized_chunk]
            updated_page = existing_page.model_copy(update={"chunks": updated_chunks})
            updated_pages = self.pages.copy()
            updated_pages[page_index] = updated_page
        else:
            # Create new page with chunk
            new_page = Page(document_id=self.id, page_number=page_number, text="", chunks=[normalized_chunk])
            updated_pages = [*self.pages, new_page]
        
        return self.model_copy(update={"pages": updated_pages})
