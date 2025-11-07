from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class Metadata(BaseModel):
    """Metadata describing additional context for a chunk."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    document_id: str
    page_number: int
    chunk_id: str
    start_offset: int
    end_offset: int
    title: Optional[str] = None
    summary: Optional[str] = None
    keywords: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class Chunk(BaseModel):
    """Represents a chunk of text derived from a document page."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    document_id: str
    page_number: int
    text: str
    start_offset: int
    end_offset: int
    cleaned_text: Optional[str] = None
    metadata: Optional[Metadata] = None


class Page(BaseModel):
    """A single page from a document, containing zero or more chunks."""

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
