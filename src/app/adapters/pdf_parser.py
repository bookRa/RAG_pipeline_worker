"""Placeholder adapter for PDF parsing."""

from __future__ import annotations

from typing import Sequence

from ..application.interfaces import DocumentParser


class PdfParserAdapter(DocumentParser):
    """Stub PDF parser returning a single-page placeholder."""

    supported_types: Sequence[str] = ("pdf",)

    def supports_type(self, file_type: str) -> bool:
        return file_type.lower() in self.supported_types

    def parse(self, file_bytes: bytes, filename: str) -> list[str]:
        size = len(file_bytes)
        return [f"PDF parser stub output for {filename} ({size} bytes)"]
