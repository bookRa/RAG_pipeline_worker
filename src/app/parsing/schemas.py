from __future__ import annotations

from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    """Normalized bounding box coordinates for visual elements."""

    x: float
    y: float
    width: float
    height: float


class ParsedParagraph(BaseModel):
    """Paragraph element returned by the parsing LLM."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    order: int
    text: str
    bbox: Optional[BoundingBox] = None


class ParsedTableCell(BaseModel):
    row: int
    column: int
    text: str


class ParsedTable(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    order: int
    caption: Optional[str] = None
    cells: list[ParsedTableCell] = Field(default_factory=list)
    bbox: Optional[BoundingBox] = None


class ParsedFigure(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    order: int
    caption: Optional[str] = None
    description: Optional[str] = None
    bbox: Optional[BoundingBox] = None
    data_uri: Optional[str] = None  # base64 image snippets when available


class ParsedPage(BaseModel):
    """Structured page representation returned by the parser."""

    document_id: str
    page_number: int
    raw_text: str
    paragraphs: list[ParsedParagraph] = Field(default_factory=list)
    tables: list[ParsedTable] = Field(default_factory=list)
    figures: list[ParsedFigure] = Field(default_factory=list)
    pixmap_path: Optional[str] = None
    pixmap_size_bytes: Optional[int] = None


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
