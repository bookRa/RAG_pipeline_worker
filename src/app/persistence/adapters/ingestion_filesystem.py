from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..ports import IngestionRepository


class FileSystemIngestionRepository(IngestionRepository):
    """Stores uploaded files under document-scoped folders."""

    def __init__(self, base_dir: Path | str) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def store(self, *, document_id: str, filename: str, data: bytes) -> str:
        document_dir = self.base_dir / document_id
        document_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(filename or "document").suffix or ".bin"
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        stored_name = f"{timestamp}{suffix}"
        destination = document_dir / stored_name
        with destination.open("wb") as handle:
            handle.write(data)
        return str(destination)
