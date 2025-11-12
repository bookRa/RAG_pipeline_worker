from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict


class PixmapGenerationError(RuntimeError):
    """Raised when pixmap rendering fails."""


@dataclass(frozen=True)
class PixmapInfo:
    """Metadata describing a rendered pixmap file."""

    page_number: int
    path: Path
    size_bytes: int


class PixmapFactory:
    """Renders PDF pages to 300 DPI PNG pixmaps for multi-modal parsing."""

    def __init__(self, base_dir: Path, dpi: int = 300) -> None:
        self.base_dir = base_dir
        self.dpi = dpi
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, document_id: str, pdf_bytes: bytes) -> Dict[int, PixmapInfo]:
        """Render every PDF page to disk and return metadata per page."""

        try:
            import fitz  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise PixmapGenerationError(
                "PyMuPDF is required for pixmap generation. Install `pymupdf`."
            ) from exc

        try:
            pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as exc:  # pragma: no cover - defensive logging
            raise PixmapGenerationError(f"Unable to read PDF bytes: {exc}") from exc

        output_dir = self.base_dir / document_id
        output_dir.mkdir(parents=True, exist_ok=True)
        pixmap_info: Dict[int, PixmapInfo] = {}

        for index, page in enumerate(pdf_document, start=1):
            try:
                pix = page.get_pixmap(dpi=self.dpi)
            except Exception as exc:  # pragma: no cover - defensive logging
                raise PixmapGenerationError(f"Failed to render pixmap for page {index}: {exc}") from exc

            file_path = output_dir / f"page_{index:04d}.png"
            pix.save(file_path)
            pixmap_info[index] = PixmapInfo(
                page_number=index,
                path=file_path,
                size_bytes=file_path.stat().st_size,
            )

        return pixmap_info
