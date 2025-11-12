from __future__ import annotations

from pathlib import Path
import time
from time import perf_counter
from typing import Sequence
import logging

from ..application.interfaces import DocumentParser, ObservabilityRecorder, ParsingLLM
from ..parsing.schemas import ParsedPage
from ..domain.models import Document, Page
from ..parsing.pixmap_factory import PixmapFactory, PixmapGenerationError, PixmapInfo

logger = logging.getLogger(__name__)


class ParsingService:
    """Converts an ingested document into a structured set of pages."""

    def __init__(
        self,
        observability: ObservabilityRecorder,
        latency: float = 0.0,
        parsers: Sequence[DocumentParser] | None = None,
        structured_parser: ParsingLLM | None = None,
        *,
        include_images: bool = False,
        pixmap_dir: Path | None = None,
        pixmap_dpi: int = 300,
        max_pixmap_bytes: int = 8_000_000,
        pixmap_max_width: int | None = None,
        pixmap_max_height: int | None = None,
        pixmap_resize_quality: str = "LANCZOS",
        pixmap_generator: PixmapFactory | None = None,
    ) -> None:
        self.observability = observability
        self.latency = latency
        self.parsers = list(parsers or [])
        self.structured_parser = structured_parser
        self.include_images = include_images and structured_parser is not None
        self.pixmap_dir = (pixmap_dir or Path("artifacts/pixmaps")).resolve()
        self.pixmap_dpi = pixmap_dpi
        self.max_pixmap_bytes = max_pixmap_bytes
        self.pixmap_generator = pixmap_generator
        if self.include_images and self.pixmap_generator is None:
            self.pixmap_generator = PixmapFactory(
                self.pixmap_dir,
                dpi=self.pixmap_dpi,
                max_width=pixmap_max_width,
                max_height=pixmap_max_height,
                resize_quality=pixmap_resize_quality,
            )

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
        pixmap_assets_meta = document.metadata.get("pixmap_assets", {}).copy()
        pixmap_metrics = document.metadata.get("pixmap_metrics", {}).copy()
        pixmap_map = self._render_pixmaps(document.id, payload, document.file_type)
        structured_latencies_ms: list[float] = []
        pixmap_total_bytes = 0
        pixmap_attached = 0
        pixmap_skipped = 0

        if parser and payload:
            page_texts = parser.parse(payload, document.filename)
            for index, text in enumerate(page_texts, start=1):
                updated_document = updated_document.add_page(Page(document_id=document.id, page_number=index, text=text))
                pages_added += 1
                if self.structured_parser:
                    pixmap_info, skipped = self._pixmap_for_page(pixmap_map, index)
                    if pixmap_info:
                        pixmap_total_bytes += pixmap_info.size_bytes
                        pixmap_attached += 1
                        pixmap_assets_meta[str(index)] = str(pixmap_info.path)
                    else:
                        pixmap_skipped += skipped
                    # For image-only parsing, pass empty string for raw_text when pixmap is available
                    parsed_page, latency = self._run_structured_parser(
                        document_id=document.id,
                        page_number=index,
                        raw_text="" if pixmap_info else text,  # Empty string when using vision parsing
                        pixmap_path=str(pixmap_info.path) if pixmap_info else None,
                    )
                    if pixmap_info:
                        parsed_page = parsed_page.model_copy(
                            update={
                                "pixmap_path": str(pixmap_info.path),
                                "pixmap_size_bytes": pixmap_info.size_bytes,
                            }
                        )
                    structured_latencies_ms.append(latency)
                    parsed_pages_meta[str(index)] = parsed_page.model_dump()

        if pages_added == 0:
            placeholder_text = (
                f"Parsed placeholder text for {document.filename}. "
                f"Approximate size: {document.size_bytes} bytes."
            )
            updated_document = updated_document.add_page(Page(document_id=document.id, page_number=1, text=placeholder_text))
            if self.structured_parser:
                pixmap_info, skipped = self._pixmap_for_page(pixmap_map, 1)
                if pixmap_info:
                    pixmap_total_bytes += pixmap_info.size_bytes
                    pixmap_attached += 1
                    pixmap_assets_meta["1"] = str(pixmap_info.path)
                else:
                    pixmap_skipped += skipped
                # For image-only parsing, pass empty string for raw_text when pixmap is available
                parsed_page, latency = self._run_structured_parser(
                    document_id=document.id,
                    page_number=1,
                    raw_text="" if pixmap_info else placeholder_text,  # Empty string when using vision parsing
                    pixmap_path=str(pixmap_info.path) if pixmap_info else None,
                )
                if pixmap_info:
                    parsed_page = parsed_page.model_copy(
                        update={
                            "pixmap_path": str(pixmap_info.path),
                            "pixmap_size_bytes": pixmap_info.size_bytes,
                        }
                    )
                structured_latencies_ms.append(latency)
                parsed_pages_meta["1"] = parsed_page.model_dump()

        updated_metadata = document.metadata.copy()
        if parsed_pages_meta:
            updated_metadata["parsed_pages"] = parsed_pages_meta
        if pixmap_assets_meta:
            updated_metadata["pixmap_assets"] = pixmap_assets_meta
        avg_latency = (
            round(sum(structured_latencies_ms) / len(structured_latencies_ms), 2)
            if structured_latencies_ms
            else None
        )
        pixmap_metrics.update(
            {
                "generated": len(pixmap_map),
                "attached": pixmap_attached,
                "skipped": pixmap_skipped,
                "total_size_bytes": pixmap_total_bytes,
                "dpi": self.pixmap_dpi if self.include_images else None,
                "avg_structured_latency_ms": avg_latency,
            }
        )
        if pixmap_metrics:
            updated_metadata["pixmap_metrics"] = pixmap_metrics

        updated_document = updated_document.model_copy(update={"status": "parsed", "metadata": updated_metadata})

        self.observability.record_event(
            stage="parsing",
            details={
                "document_id": updated_document.id,
                "page_count": len(updated_document.pages),
                "parser_used": parser.__class__.__name__ if parser else "placeholder",
                "pixmap": pixmap_metrics,
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
        pixmap_path: str | None = None,
    ) -> tuple[ParsedPage, float]:
        assert self.structured_parser  # for mypy
        start = perf_counter()
        parsed_page = self.structured_parser.parse_page(
            document_id=document_id,
            page_number=page_number,
            raw_text=raw_text,
            pixmap_path=pixmap_path,
        )
        duration_ms = (perf_counter() - start) * 1000
        parsed_page = parsed_page.model_copy(
            update={
                "pixmap_path": getattr(parsed_page, "pixmap_path", None) or pixmap_path,
                "pixmap_size_bytes": getattr(parsed_page, "pixmap_size_bytes", None),
            }
        )
        return parsed_page, duration_ms

    def _render_pixmaps(self, document_id: str, payload: bytes | None, file_type: str) -> dict[int, PixmapInfo]:
        if not (self.include_images and payload and file_type.lower() == "pdf" and self.pixmap_generator):
            return {}
        try:
            return self.pixmap_generator.generate(document_id, payload)
        except PixmapGenerationError as exc:
            logger.warning("Failed to generate pixmaps for %s: %s", document_id, exc)
            return {}

    def _pixmap_for_page(self, pixmap_map: dict[int, PixmapInfo], page_number: int) -> tuple[PixmapInfo | None, int]:
        info = pixmap_map.get(page_number)
        if not info:
            return None, 0
        if info.size_bytes > self.max_pixmap_bytes:
            logger.warning(
                "Skipping pixmap for doc page=%s due to size %s > limit %s",
                page_number,
                info.size_bytes,
                self.max_pixmap_bytes,
            )
            return None, 1
        return info, 0
