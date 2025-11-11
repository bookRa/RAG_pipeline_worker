from __future__ import annotations

from pathlib import Path
import time
from typing import Sequence

from ..application.interfaces import DocumentParser, ObservabilityRecorder, ParsingLLM
from ..parsing.schemas import ParsedPage
from ..domain.models import Document, Page


class ParsingService:
    """Converts an ingested document into a structured set of pages."""

    def __init__(
        self,
        observability: ObservabilityRecorder,
        latency: float = 0.0,
        parsers: Sequence[DocumentParser] | None = None,
        structured_parser: ParsingLLM | None = None,
    ) -> None:
        self.observability = observability
        self.latency = latency
        self.parsers = list(parsers or [])
        self.structured_parser = structured_parser

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
        parsed_pages_meta = document.metadata.get("parsed_pages", {}).copy()

        if parser and payload:
            page_texts = parser.parse(payload, document.filename)
            for index, text in enumerate(page_texts, start=1):
                updated_document = updated_document.add_page(Page(document_id=document.id, page_number=index, text=text))
                pages_added += 1
                if self.structured_parser:
                    parsed_page = self._run_structured_parser(
                        document_id=document.id,
                        page_number=index,
                        raw_text=text,
                    )
                    parsed_pages_meta[str(index)] = parsed_page.model_dump()

        if pages_added == 0:
            placeholder_text = (
                f"Parsed placeholder text for {document.filename}. "
                f"Approximate size: {document.size_bytes} bytes."
            )
            updated_document = updated_document.add_page(Page(document_id=document.id, page_number=1, text=placeholder_text))
            if self.structured_parser:
                parsed_pages_meta["1"] = ParsedPage(
                    document_id=document.id,
                    page_number=1,
                    raw_text=placeholder_text,
                ).model_dump()

        updated_metadata = document.metadata.copy()
        if parsed_pages_meta:
            updated_metadata["parsed_pages"] = parsed_pages_meta

        updated_document = updated_document.model_copy(update={"status": "parsed", "metadata": updated_metadata})

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

    def _run_structured_parser(
        self,
        *,
        document_id: str,
        page_number: int,
        raw_text: str,
    ) -> ParsedPage:
        assert self.structured_parser  # for mypy
        return self.structured_parser.parse_page(
            document_id=document_id,
            page_number=page_number,
            raw_text=raw_text,
            pixmap_path=None,
        )
