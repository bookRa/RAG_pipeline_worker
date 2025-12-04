from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ...domain.models import Document
from ..ports import DocumentRepository


def _get_page_cleaning_metadata(cleaning_metadata: dict[Any, dict], page_number: int) -> dict:
    """Return cleaning metadata for a page regardless of key serialization."""
    if not cleaning_metadata:
        return {}
    return cleaning_metadata.get(page_number) or cleaning_metadata.get(str(page_number)) or {}


class FileSystemDocumentRepository(DocumentRepository):
    """Stores documents as JSON blobs on disk."""

    def __init__(self, base_dir: Path | str) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, document: Document) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
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
    
    def approve_segment(self, document_id: str, segment_id: str) -> bool:
        """Mark a segment as reviewed/approved."""
        document = self.get(document_id)
        if not document:
            return False
        
        # Update segment review status in cleaning metadata
        updated = False
        cleaning_metadata = document.metadata.get("cleaning_metadata_by_page", {}) if document.metadata else {}
        
        for page_num, page_meta in cleaning_metadata.items():
            llm_segments = page_meta.get("llm_segments", {})
            segments = llm_segments.get("segments", [])
            
            for segment in segments:
                if segment.get("segment_id") == segment_id:
                    segment["needs_review"] = False
                    # Store review decision
                    if "review_history" not in segment:
                        segment["review_history"] = []
                    segment["review_history"].append({
                        "action": "approved",
                        "timestamp": datetime.utcnow().isoformat(),
                    })
                    updated = True
                    break
            
            if updated:
                break
        
        if updated:
            # Save updated document
            self.save(document)
        
        return updated
    
    def edit_segment(self, document_id: str, segment_id: str, corrected_text: str) -> bool:
        """Update a segment with corrected text from human reviewer."""
        document = self.get(document_id)
        if not document:
            return False
        
        # Update segment text in cleaning metadata
        updated = False
        cleaning_metadata = document.metadata.get("cleaning_metadata_by_page", {}) if document.metadata else {}
        
        for page_num, page_meta in cleaning_metadata.items():
            llm_segments = page_meta.get("llm_segments", {})
            segments = llm_segments.get("segments", [])
            
            for segment in segments:
                if segment.get("segment_id") == segment_id:
                    original_text = segment.get("text", "")
                    segment["text"] = corrected_text
                    segment["needs_review"] = False
                    # Store review decision and correction
                    if "review_history" not in segment:
                        segment["review_history"] = []
                    segment["review_history"].append({
                        "action": "edited",
                        "original_text": original_text,
                        "corrected_text": corrected_text,
                        "timestamp": datetime.utcnow().isoformat(),
                    })
                    updated = True
                    break
            
            if updated:
                break
        
        if updated:
            # Also update cleaned_text on the page if needed
            # This is a simplified approach - in production you might want to regenerate cleaned_text
            for page in document.pages:
                page_meta = _get_page_cleaning_metadata(cleaning_metadata, page.page_number)
                llm_segments = page_meta.get("llm_segments", {})
                segments = llm_segments.get("segments", [])
                if any(s.get("segment_id") == segment_id for s in segments):
                    # Rebuild cleaned_text from segments
                    cleaned_parts = [s.get("text", "") for s in segments]
                    updated_page = page.model_copy(update={"cleaned_text": " ".join(cleaned_parts)})
                    document = document.model_copy(
                        update={
                            "pages": [
                                p if p.page_number != page.page_number else updated_page
                                for p in document.pages
                            ]
                        }
                    )
                    break
            
            # Save updated document
            self.save(document)
        
        return updated