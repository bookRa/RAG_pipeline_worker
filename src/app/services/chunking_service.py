from __future__ import annotations

import logging
import time
from uuid import uuid4

from typing import Any

from ..application.interfaces import ObservabilityRecorder
from ..domain.models import Chunk, Document, Metadata
from ..parsing.schemas import ParsedPage, ParsedTextComponent, ParsedImageComponent, ParsedTableComponent

logger = logging.getLogger(__name__)


class ChunkingService:
    """Splits document pages into smaller, retrievable chunks."""

    def __init__(
        self,
        observability: ObservabilityRecorder,
        latency: float = 0.0,
        chunk_size: int = 200,
        chunk_overlap: int = 50,
        text_splitter: Any | None = None,
        strategy: str = "component",  # NEW: "component", "hybrid", "fixed"
        component_merge_threshold: int = 100,  # NEW: Merge small components below this token count
        max_component_tokens: int = 500,  # NEW: Split large components above this token count
    ) -> None:
        self.observability = observability
        self.latency = latency
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.text_splitter = text_splitter
        self.strategy = strategy
        self.component_merge_threshold = component_merge_threshold
        self.max_component_tokens = max_component_tokens

    def _simulate_latency(self) -> None:
        if self.latency > 0:
            time.sleep(self.latency)

    def chunk(self, document: Document, size: int | None = None, overlap: int | None = None) -> Document:
        self._simulate_latency()
        
        logger.info(
            "🔨 Starting chunking for doc=%s with strategy=%s",
            document.id,
            self.strategy,
        )
        
        # Route to appropriate chunking strategy
        if self.strategy == "component":
            return self._chunk_by_components(document, size, overlap)
        elif self.strategy == "hybrid":
            return self._chunk_hybrid(document, size, overlap)
        else:
            # Default: fixed-size chunking (existing behavior)
            return self._chunk_fixed_size(document, size, overlap)
    
    def _chunk_fixed_size(self, document: Document, size: int | None = None, overlap: int | None = None) -> Document:
        """Original fixed-size chunking strategy (legacy)."""
        size = size or self.chunk_size
        overlap = overlap if overlap is not None else self.chunk_overlap
        normalized_overlap = min(overlap, size - 1) if size > 1 else 0
        updated_document = document
        parsed_pages_meta = document.metadata.get("parsed_pages", {})

        for page in document.pages:
            if page.chunks:
                continue

            raw_text = page.text or ""
            if not raw_text:
                continue

            cleaned_text = page.cleaned_text
            parsed_page = parsed_pages_meta.get(str(page.page_number)) or parsed_pages_meta.get(str(page.page_number))

            segments = self._split_text(raw_text, size, normalized_overlap)
            cursor = 0
            chunk_index = 0

            for segment in segments:
                start = self._find_segment_start(raw_text, segment, cursor)
                end = start + len(segment)
                cursor = end

                chunk_id = str(uuid4())
                chunk_raw_text = raw_text[start:end]
                chunk_cleaned_text = cleaned_text[start:end] if cleaned_text else None
                if chunk_cleaned_text is not None:
                    chunk_cleaned_text = chunk_cleaned_text.rstrip()

                # Attach cleaning metadata from document metadata if available
                # Cleaning service stores metadata keyed by page_number
                chunk_extra = {}
                cleaning_metadata_by_page = document.metadata.get("cleaning_metadata_by_page", {})
                if page.page_number in cleaning_metadata_by_page:
                    page_cleaning_meta = cleaning_metadata_by_page[page.page_number].copy()
                    # Add segment_id (chunk.id) to link metadata to this chunk
                    page_cleaning_meta["segment_id"] = chunk_id
                    chunk_extra["cleaning"] = page_cleaning_meta

                parsed_matches = self._match_parsed_segments(chunk_raw_text, parsed_page)
                if parsed_matches:
                    chunk_extra["parsed_segments"] = parsed_matches

                metadata = Metadata(
                    document_id=document.id,
                    page_number=page.page_number,
                    chunk_id=chunk_id,
                    start_offset=start,
                    end_offset=end,
                    title=f"{document.filename}-p{page.page_number}-c{chunk_index}",
                    extra=chunk_extra,
                )
                chunk = Chunk(
                    id=chunk_id,
                    document_id=document.id,
                    page_number=page.page_number,
                    text=chunk_raw_text,  # Always raw text slice
                    cleaned_text=chunk_cleaned_text,  # Cleaned slice if available
                    start_offset=start,  # Offsets reference raw text positions
                    end_offset=end,
                    metadata=metadata,
                )
                updated_document = updated_document.add_chunk(page.page_number, chunk)

                chunk_index += 1
                if not self.text_splitter and end < len(raw_text):
                    next_cursor = max(end - normalized_overlap, 0)
                    if next_cursor <= start:
                        next_cursor = start + 1
                    cursor = next_cursor

        updated_document = updated_document.model_copy(update={"status": "chunked"})
        self.observability.record_event(
            stage="chunking",
            details={
                "document_id": updated_document.id,
                "page_count": len(updated_document.pages),
                "chunk_count": sum(len(page.chunks) for page in updated_document.pages),
            },
        )
        return updated_document

    @staticmethod
    def _match_parsed_segments(chunk_text: str, parsed_page: dict | None) -> list[dict[str, str]]:
        """Match chunk text against components in parsed page."""
        if not parsed_page:
            return []
        matches: list[dict[str, str]] = []
        components = parsed_page.get("components", [])
        
        for component in components:
            component_type = component.get("type", "")
            component_id = component.get("id", "")
            component_order = component.get("order", 0)
            
            # Extract text based on component type
            text_to_match = ""
            if component_type == "text":
                text_to_match = (component.get("text") or "").strip()
            elif component_type == "image":
                # Match against recognized_text and description
                recognized = (component.get("recognized_text") or "").strip()
                description = (component.get("description") or "").strip()
                text_to_match = f"{recognized} {description}".strip()
            elif component_type == "table":
                # Match against all row values
                rows = component.get("rows", [])
                row_texts = []
                for row in rows:
                    if isinstance(row, dict):
                        row_texts.extend(str(v).strip() for v in row.values() if v)
                text_to_match = " ".join(row_texts)
            
            # Check if component text appears in chunk
            if text_to_match and text_to_match in chunk_text:
                matches.append({
                    "id": component_id,
                    "order": str(component_order),
                    "type": component_type,
                })
        
        return matches

    def _split_text(self, text: str, size: int, overlap: int) -> list[str]:
        if self.text_splitter:
            try:
                return [segment for segment in self.text_splitter.split_text(text) if segment.strip()]
            except AttributeError:
                # Fallback to manual logic if the injected splitter does not support split_text
                pass

        segments: list[str] = []
        cursor = 0
        while cursor < len(text):
            end = min(len(text), cursor + size)
            segments.append(text[cursor:end])
            if end == len(text):
                break
            next_cursor = max(end - overlap, 0)
            if next_cursor <= cursor:
                next_cursor = cursor + 1
            cursor = next_cursor
        return segments

    @staticmethod
    def _find_segment_start(text: str, segment: str, cursor: int) -> int:
        idx = text.find(segment, cursor)
        if idx == -1:
            return cursor
        return idx
    
    def _chunk_by_components(self, document: Document, size: int | None = None, overlap: int | None = None) -> Document:
        """Component-aware chunking strategy: chunk based on parsed components."""
        updated_document = document
        parsed_pages_meta = document.metadata.get("parsed_pages", {})
        
        # Use provided size/overlap or fall back to instance defaults
        chunk_size = size if size is not None else self.chunk_size
        chunk_overlap = overlap if overlap is not None else self.chunk_overlap
        
        total_chunks_created = 0
        
        for page in document.pages:
            if page.chunks:
                continue
            
            # Get parsed page components
            parsed_page_data = parsed_pages_meta.get(str(page.page_number))
            if not parsed_page_data:
                logger.warning(
                    "⚠️ No parsed components for doc=%s page=%s, falling back to fixed-size chunking",
                    document.id,
                    page.page_number,
                )
                # Fallback to fixed-size for this page
                updated_document = self._chunk_page_fixed_size(
                    updated_document, page, chunk_size, chunk_overlap
                )
                continue
            
            # Parse page from metadata
            try:
                parsed_page = ParsedPage.model_validate(parsed_page_data)
            except Exception as exc:
                logger.warning(
                    "⚠️ Failed to validate parsed page for doc=%s page=%s: %s",
                    document.id,
                    page.page_number,
                    exc,
                )
                continue
            
            logger.info(
                "📑 Processing page %d with %d components",
                page.page_number,
                len(parsed_page.components),
            )
            
            # Group components into chunks
            component_groups = self._group_components(parsed_page.components)
            
            logger.info(
                "✂️ Grouped %d components into %d chunks",
                len(parsed_page.components),
                len(component_groups),
            )
            
            # Create chunks from component groups
            for group_index, component_group in enumerate(component_groups):
                chunk = self._create_chunk_from_components(
                    component_group=component_group,
                    page=page,
                    document=document,
                    chunk_index=group_index,
                    parsed_page=parsed_page,
                )
                if chunk:
                    updated_document = updated_document.add_chunk(page.page_number, chunk)
                    total_chunks_created += 1
        
        updated_document = updated_document.model_copy(update={"status": "chunked"})
        
        logger.info(
            "✅ Component chunking complete: created %d chunks across %d pages",
            total_chunks_created,
            len(document.pages),
        )
        
        self.observability.record_event(
            stage="chunking",
            details={
                "document_id": updated_document.id,
                "strategy": "component",
                "page_count": len(updated_document.pages),
                "chunk_count": total_chunks_created,
            },
        )
        return updated_document
    
    def _group_components(
        self,
        components: list[ParsedTextComponent | ParsedImageComponent | ParsedTableComponent],
    ) -> list[list[ParsedTextComponent | ParsedImageComponent | ParsedTableComponent]]:
        """Group components into chunks based on size thresholds."""
        groups = []
        current_group = []
        current_tokens = 0
        
        for component in components:
            component_text = self._extract_component_text(component)
            component_tokens = len(component_text.split())
            
            # Strategy: Large components become standalone chunks
            if component_tokens > self.max_component_tokens:
                # Flush current group if any
                if current_group:
                    groups.append(current_group)
                    current_group = []
                    current_tokens = 0
                
                # Large component gets its own chunk (could be split further but keeping simple for now)
                groups.append([component])
                logger.debug(
                    "📦 Large component (type=%s, tokens=%d) -> standalone chunk",
                    component.type,
                    component_tokens,
                )
            
            # Strategy: Merge small components until threshold
            elif current_tokens + component_tokens < self.component_merge_threshold:
                current_group.append(component)
                current_tokens += component_tokens
                logger.debug(
                    "➕ Adding component (type=%s, tokens=%d) to current group (total=%d)",
                    component.type,
                    component_tokens,
                    current_tokens,
                )
            
            # Strategy: Current group is full, start new group
            else:
                if current_group:
                    groups.append(current_group)
                    logger.debug(
                        "📦 Flushing group with %d components (%d tokens)",
                        len(current_group),
                        current_tokens,
                    )
                current_group = [component]
                current_tokens = component_tokens
        
        # Flush remaining group
        if current_group:
            groups.append(current_group)
            logger.debug(
                "📦 Final group with %d components (%d tokens)",
                len(current_group),
                current_tokens,
            )
        
        return groups
    
    @staticmethod
    def _extract_component_text(
        component: ParsedTextComponent | ParsedImageComponent | ParsedTableComponent
    ) -> str:
        """Extract text content from a component for token counting."""
        if isinstance(component, ParsedTextComponent):
            return component.text
        elif isinstance(component, ParsedImageComponent):
            # For images, use description + recognized text
            parts = []
            if component.description:
                parts.append(component.description)
            if component.recognized_text:
                parts.append(component.recognized_text)
            return " ".join(parts)
        elif isinstance(component, ParsedTableComponent):
            # For tables, extract all row values or use summary if available
            if component.table_summary:
                return component.table_summary
            row_texts = []
            for row in component.rows:
                row_texts.extend(str(v) for v in row.values() if v)
            return " ".join(row_texts)
        return ""
    
    def _create_chunk_from_components(
        self,
        component_group: list[ParsedTextComponent | ParsedImageComponent | ParsedTableComponent],
        page: Any,
        document: Document,
        chunk_index: int,
        parsed_page: ParsedPage,
    ) -> Chunk | None:
        """Create a chunk from a group of components."""
        if not component_group:
            return None
        
        # Extract text from all components in group
        component_texts = [self._extract_component_text(comp) for comp in component_group]
        combined_raw_text = "\n\n".join(component_texts)
        
        # Get first and last component for metadata
        first_comp = component_group[0]
        last_comp = component_group[-1]
        
        # For cleaned text, try to find the corresponding slice from page.cleaned_text
        # For now, use the combined raw text as cleaned text (can be enhanced)
        chunk_cleaned_text = combined_raw_text if page.cleaned_text else None
        
        # Generate chunk ID
        chunk_id = str(uuid4())
        
        # Build metadata with component context
        component_type = first_comp.type
        component_id = first_comp.id
        component_order = first_comp.order
        
        # Add component-specific metadata
        component_description = None
        component_summary = None
        
        if isinstance(first_comp, ParsedImageComponent):
            component_description = first_comp.description
        elif isinstance(first_comp, ParsedTableComponent):
            component_summary = first_comp.table_summary
        
        # Attach cleaning metadata if available
        chunk_extra = {}
        cleaning_metadata_by_page = document.metadata.get("cleaning_metadata_by_page", {})
        if page.page_number in cleaning_metadata_by_page:
            page_cleaning_meta = cleaning_metadata_by_page[page.page_number].copy()
            page_cleaning_meta["segment_id"] = chunk_id
            chunk_extra["cleaning"] = page_cleaning_meta
        
        # Add component info to extra
        chunk_extra["component_group"] = [
            {
                "id": comp.id,
                "type": comp.type,
                "order": comp.order,
            }
            for comp in component_group
        ]
        
        metadata = Metadata(
            document_id=document.id,
            page_number=page.page_number,
            chunk_id=chunk_id,
            start_offset=0,  # Component-based chunks don't have meaningful offsets in raw text
            end_offset=len(combined_raw_text),
            title=f"{document.filename}-p{page.page_number}-c{chunk_index}",
            component_id=component_id,
            component_type=component_type,
            component_order=component_order,
            component_description=component_description,
            component_summary=component_summary,
            document_title=document.filename,
            page_summary=parsed_page.page_summary,
            extra=chunk_extra,
        )
        
        chunk = Chunk(
            id=chunk_id,
            document_id=document.id,
            page_number=page.page_number,
            text=combined_raw_text,
            cleaned_text=chunk_cleaned_text,
            start_offset=0,
            end_offset=len(combined_raw_text),
            metadata=metadata,
        )
        
        logger.debug(
            "✨ Created chunk from %d components (type=%s, tokens=%d)",
            len(component_group),
            component_type,
            len(combined_raw_text.split()),
        )
        
        return chunk
    
    def _chunk_hybrid(self, document: Document, size: int | None = None, overlap: int | None = None) -> Document:
        """Hybrid strategy: component-aware with fixed-size fallback."""
        # For now, just use component-based chunking
        # Future: Could implement component-aware boundaries with fixed-size splitting
        return self._chunk_by_components(document)
    
    def _chunk_page_fixed_size(
        self,
        document: Document,
        page: Any,
        size: int,
        overlap: int,
    ) -> Document:
        """Chunk a single page using fixed-size strategy."""
        raw_text = page.text or ""
        if not raw_text:
            return document
        
        cleaned_text = page.cleaned_text
        normalized_overlap = min(overlap, size - 1) if size > 1 else 0
        
        segments = self._split_text(raw_text, size, normalized_overlap)
        cursor = 0
        chunk_index = 0
        
        updated_document = document
        
        for segment in segments:
            start = self._find_segment_start(raw_text, segment, cursor)
            end = start + len(segment)
            cursor = end
            
            chunk_id = str(uuid4())
            chunk_raw_text = raw_text[start:end]
            chunk_cleaned_text = cleaned_text[start:end] if cleaned_text else None
            if chunk_cleaned_text is not None:
                chunk_cleaned_text = chunk_cleaned_text.rstrip()
            
            chunk_extra = {}
            cleaning_metadata_by_page = document.metadata.get("cleaning_metadata_by_page", {})
            if page.page_number in cleaning_metadata_by_page:
                page_cleaning_meta = cleaning_metadata_by_page[page.page_number].copy()
                page_cleaning_meta["segment_id"] = chunk_id
                chunk_extra["cleaning"] = page_cleaning_meta
            
            metadata = Metadata(
                document_id=document.id,
                page_number=page.page_number,
                chunk_id=chunk_id,
                start_offset=start,
                end_offset=end,
                title=f"{document.filename}-p{page.page_number}-c{chunk_index}",
                extra=chunk_extra,
            )
            
            chunk = Chunk(
                id=chunk_id,
                document_id=document.id,
                page_number=page.page_number,
                text=chunk_raw_text,
                cleaned_text=chunk_cleaned_text,
                start_offset=start,
                end_offset=end,
                metadata=metadata,
            )
            
            updated_document = updated_document.add_chunk(page.page_number, chunk)
            chunk_index += 1
            
            if end < len(raw_text):
                next_cursor = max(end - normalized_overlap, 0)
                if next_cursor <= start:
                    next_cursor = start + 1
                cursor = next_cursor
        
        return updated_document
