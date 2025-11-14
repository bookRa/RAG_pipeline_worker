from __future__ import annotations

from typing import Literal, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class BoundingBox(BaseModel):
    """Normalized bounding box coordinates for visual elements."""

    x: float
    y: float
    width: float
    height: float


class ParsedTextComponent(BaseModel):
    """Text component (paragraphs, headings, captions, labels)."""

    type: Literal["text"] = "text"
    id: str = Field(default_factory=lambda: str(uuid4()))
    order: int
    text: str
    text_type: Optional[str] = Field(
        default=None,
        description="Type of text element: 'paragraph', 'heading', 'caption', 'label', etc.",
    )
    bbox: Optional[BoundingBox] = None


class ParsedImageComponent(BaseModel):
    """Image component with detailed visual description and recognized text."""

    type: Literal["image"] = "image"
    id: str = Field(default_factory=lambda: str(uuid4()))
    order: int
    description: str = Field(
        description="REQUIRED - Detailed visual description of what is shown in the image. Describe what you see visually, not text captions that may appear near the image."
    )
    recognized_text: Optional[str] = Field(
        default=None,
        description="Any text visible within the image itself (OCR results from text embedded in the image)",
    )
    bbox: Optional[BoundingBox] = None


class ParsedTableComponent(BaseModel):
    """Table component with flexible row structure for merged cells."""

    type: Literal["table"] = "table"
    id: str = Field(default_factory=lambda: str(uuid4()))
    order: int
    caption: Optional[str] = Field(default=None, description="Table caption or title")
    rows: list[dict[str, str]] = Field(
        default_factory=list,
        description="List of rows, each row is a dict with variable keys (handles merged cells, different column counts)",
    )
    table_summary: Optional[str] = Field(
        default=None,
        description="LLM-generated 2-3 sentence summary of what the table shows, its purpose, and key information",
    )
    bbox: Optional[BoundingBox] = None

    @field_validator("rows")
    @classmethod
    def validate_rows(cls, v: list) -> list:
        """Ensure rows are dicts with string values."""
        for row in v:
            if not isinstance(row, dict):
                raise ValueError("Each row must be a dictionary")
            for key, value in row.items():
                if not isinstance(key, str) or not isinstance(value, str):
                    raise ValueError("Row keys and values must be strings")
        return v


# Discriminated union for components
ParsedComponent = Union[ParsedTextComponent, ParsedImageComponent, ParsedTableComponent]


class ParsedPage(BaseModel):
    """Structured page representation with ordered components preserving layout."""

    document_id: str
    page_number: int
    raw_text: str = Field(description="Full markdown representation of the page content")
    components: list[ParsedComponent] = Field(
        default_factory=list,
        description="Ordered list of components reflecting page layout (top to bottom, left to right)",
    )
    page_summary: Optional[str] = Field(
        default=None,
        description="LLM-generated summary describing the page's role in the document and key components",
    )
    pixmap_path: Optional[str] = None
    pixmap_size_bytes: Optional[int] = None
    
    # Parsing status and error tracking
    parsing_status: Literal["success", "failed", "partial"] = Field(
        default="success",
        description="Status of parsing attempt: success (fully parsed), failed (parsing error), partial (some content extracted)",
    )
    error_details: Optional[str] = Field(
        default=None,
        description="Error message if parsing failed or encountered issues",
    )
    error_type: Optional[str] = Field(
        default=None,
        description="Type of error: repetition_loop, network_error, timeout, validation_error, etc.",
    )

    # Backward compatibility helpers (for gradual migration)
    @property
    def paragraphs(self) -> list[ParsedTextComponent]:
        """Extract text components for backward compatibility."""
        return [c for c in self.components if isinstance(c, ParsedTextComponent)]

    @property
    def tables(self) -> list[ParsedTableComponent]:
        """Extract table components for backward compatibility."""
        return [c for c in self.components if isinstance(c, ParsedTableComponent)]

    @property
    def figures(self) -> list[ParsedImageComponent]:
        """Extract image components for backward compatibility."""
        return [c for c in self.components if isinstance(c, ParsedImageComponent)]


class CleanedSegment(BaseModel):
    """Normalized textual segment (paragraph/table cell/etc.)."""

    segment_id: str
    text: str
    needs_review: bool = False
    rationale: Optional[str] = None


class CleanedPage(BaseModel):
    """Cleaned view of a parsed page."""

    document_id: str
    page_number: int
    segments: list[CleanedSegment] = Field(default_factory=list)
