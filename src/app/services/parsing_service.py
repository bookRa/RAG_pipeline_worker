from __future__ import annotations

from pathlib import Path
import time
from typing import Sequence

from ..application.interfaces import DocumentParser, ObservabilityRecorder
from ..domain.models import Document, Page


class ParsingService:
    """Converts an ingested document into a structured set of pages."""

    def __init__(
        self,
        observability: ObservabilityRecorder,
        latency: float = 0.0,
        parsers: Sequence[DocumentParser] | None = None,
    ) -> None:
        self.observability = observability
        self.latency = latency
        self.parsers = list(parsers or [])

    def _simulate_latency(self) -> None:
        if self.latency > 0:
            time.sleep(self.latency)

    def parse(self, document: Document, file_bytes: bytes | None = None) -> Document:
        self._simulate_latency()
        if document.pages:
            return document

        parser = self._resolve_parser(document.file_type)
        payload = file_bytes or self._load_raw_file(document)
        pages_added = 0
        updated_document = document

        if parser and payload:
            page_texts = parser.parse(payload, document.filename)
            for index, text in enumerate(page_texts, start=1):
                updated_document = updated_document.add_page(Page(document_id=document.id, page_number=index, text=text))
                pages_added += 1

        if pages_added == 0:
            placeholder_text = (
                f"Parsed placeholder text for {document.filename}. "
                f"Approximate size: {document.size_bytes} bytes."
            )
            updated_document = updated_document.add_page(Page(document_id=document.id, page_number=1, text=placeholder_text))

        updated_document = updated_document.model_copy(update={"status": "parsed"})

        self.observability.record_event(
            stage="parsing",
            details={
                "document_id": updated_document.id,
                "page_count": len(updated_document.pages),
                "parser_used": parser.__class__.__name__ if parser else "placeholder",
            },
        )
        return updated_document

    def _resolve_parser(self, file_type: str) -> DocumentParser | None:
        normalized = file_type.lower()
        for parser in self.parsers:
            if parser.supports_type(normalized):
                return parser
        return None

    def _load_raw_file(self, document: Document) -> bytes | None:
        path_value = document.metadata.get("raw_file_path")
        if not path_value:
            return None
        try:
            return Path(path_value).read_bytes()
        except OSError:
            return None
