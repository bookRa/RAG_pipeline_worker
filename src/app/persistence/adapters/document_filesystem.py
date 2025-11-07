from __future__ import annotations

import json
from pathlib import Path

from ...domain.models import Document
from ..ports import DocumentRepository


class FileSystemDocumentRepository(DocumentRepository):
    """Stores documents as JSON blobs on disk."""

    def __init__(self, base_dir: Path | str) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, document: Document) -> None:
        target = self.base_dir / f"{document.id}.json"
        with target.open("w", encoding="utf-8") as handle:
            json.dump(document.model_dump(mode="json"), handle, indent=2)

    def get(self, document_id: str) -> Document | None:
        target = self.base_dir / f"{document_id}.json"
        if not target.exists():
            return None
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return Document.model_validate(data)

    def list(self) -> list[Document]:
        documents: list[Document] = []
        for path in sorted(self.base_dir.glob("*.json")):
            document = self.get(path.stem)
            if document:
                documents.append(document)
        return documents
