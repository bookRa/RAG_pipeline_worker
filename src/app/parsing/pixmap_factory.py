from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict


logger = logging.getLogger(__name__)


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

    def __init__(
        self,
        base_dir: Path,
        dpi: int = 300,
        max_width: int | None = None,
        max_height: int | None = None,
        resize_quality: str = "LANCZOS",
    ) -> None:
        self.base_dir = base_dir
        self.dpi = dpi
        self.max_width = max_width
        self.max_height = max_height
        self.resize_quality = resize_quality
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

            # Resize if needed to stay within max dimensions
            pix = self._resize_if_needed(pix, document_id, index)

            file_path = output_dir / f"page_{index:04d}.png"
            pix.save(file_path)
            pixmap_info[index] = PixmapInfo(
                page_number=index,
                path=file_path,
                size_bytes=file_path.stat().st_size,
            )

        return pixmap_info

    def _resize_if_needed(self, pixmap: "fitz.Pixmap", document_id: str, page_number: int) -> "fitz.Pixmap":
        """Resize pixmap if it exceeds max dimensions, maintaining aspect ratio."""
        if not self.max_width and not self.max_height:
            return pixmap

        original_width = pixmap.width
        original_height = pixmap.height

        # Check if resizing is needed
        needs_resize = False
        if self.max_width and original_width > self.max_width:
            needs_resize = True
        if self.max_height and original_height > self.max_height:
            needs_resize = True

        if not needs_resize:
            return pixmap

        # Calculate scale factor to maintain aspect ratio
        scale_x = self.max_width / original_width if self.max_width else float("inf")
        scale_y = self.max_height / original_height if self.max_height else float("inf")
        scale_factor = min(scale_x, scale_y)

        new_width = int(original_width * scale_factor)
        new_height = int(original_height * scale_factor)

        # Calculate token savings (each 512x512 tile = ~5,667 tokens)
        original_tiles = ((original_width + 511) // 512) * ((original_height + 511) // 512)
        new_tiles = ((new_width + 511) // 512) * ((new_height + 511) // 512)
        tiles_saved = original_tiles - new_tiles
        tokens_saved = tiles_saved * 5667

        logger.info(
            "Resizing pixmap for doc=%s page=%s: %dx%d -> %dx%d (scale=%.2f, tiles=%d->%d, ~%d tokens saved)",
            document_id,
            page_number,
            original_width,
            original_height,
            new_width,
            new_height,
            scale_factor,
            original_tiles,
            new_tiles,
            tokens_saved,
        )

        try:
            from PIL import Image
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise PixmapGenerationError(
                "Pillow is required for pixmap resizing. Install `pillow`."
            ) from exc

        # Get the resampling filter from PIL
        resample_filter = getattr(Image.Resampling, self.resize_quality, Image.Resampling.LANCZOS)

        # Convert fitz pixmap to PIL Image
        img = Image.frombytes("RGB", (original_width, original_height), pixmap.samples)

        # Resize using PIL
        img_resized = img.resize((new_width, new_height), resample=resample_filter)

        # Convert back to fitz pixmap using the colorspace, width, height, samples, alpha constructor
        try:
            import fitz
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise PixmapGenerationError(
                "PyMuPDF is required for pixmap generation. Install `pymupdf`."
            ) from exc

        # Create new pixmap from PIL image bytes
        # Use the constructor: Pixmap(colorspace, width, height, samples, alpha)
        resized_pixmap = fitz.Pixmap(fitz.csRGB, new_width, new_height, img_resized.tobytes(), False)

        return resized_pixmap
