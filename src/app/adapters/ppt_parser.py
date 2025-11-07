"""Placeholder adapter for PowerPoint parsing."""

from __future__ import annotations

from typing import Sequence

from ..application.interfaces import DocumentParser


class PptParserAdapter(DocumentParser):
    """Stub PPT parser returning placeholder text."""

    supported_types: Sequence[str] = ("ppt", "pptx")

    def supports_type(self, file_type: str) -> bool:
        return file_type.lower() in self.supported_types

    def parse(self, file_bytes: bytes, filename: str) -> list[str]:
        size = len(file_bytes)
        return [f"PPT parser stub output for {filename} ({size} bytes)"]
