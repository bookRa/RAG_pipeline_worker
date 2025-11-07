from __future__ import annotations

from typing import Callable, Protocol, Sequence


class TaskScheduler(Protocol):
    """Port describing how background work should be scheduled."""

    def schedule(self, func: Callable[[], None]) -> None:
        """Schedule the provided callable for asynchronous execution."""


class DocumentParser(Protocol):
    """Port for file-type specific document parsers."""

    supported_types: Sequence[str]

    def supports_type(self, file_type: str) -> bool:
        """Return True if the parser handles the provided file type."""

    def parse(self, file_bytes: bytes, filename: str) -> list[str]:
        """Parse raw bytes and return a list of page texts."""


class SummaryGenerator(Protocol):
    """Port for generating summaries (LLM, heuristics, etc.)."""

    def summarize(self, text: str) -> str:
        """Return a short summary of the provided text."""
