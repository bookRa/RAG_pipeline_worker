from __future__ import annotations

import logging
import time

from ..application.interfaces import SummaryGenerator, ObservabilityRecorder
from ..domain.models import Document

logger = logging.getLogger(__name__)


class EnrichmentService:
    """Adds lightweight metadata such as titles and summaries to chunks."""

    def __init__(
        self,
        observability: ObservabilityRecorder,
        latency: float = 0.0,
        summary_generator: SummaryGenerator | None = None,
        use_llm_summarization: bool = True,
    ) -> None:
        self.observability = observability
        self.latency = latency
        self.summary_generator = summary_generator
        self.use_llm_summarization = use_llm_summarization

    def _simulate_latency(self) -> None:
        if self.latency > 0:
            time.sleep(self.latency)

    def enrich(self, document: Document) -> Document:
        self._simulate_latency()
        
        logger.info(
            "✨ Starting enrichment for doc=%s (%d pages, use_llm=%s)",
            document.id,
            len(document.pages),
            self.use_llm_summarization,
        )
        
        # FIRST: Generate document-level summary
        document_summary = self._generate_document_summary(document)
        
        logger.info(
            "📄 Generated document summary: %s",
            document_summary[:100] + ("..." if len(document_summary) > 100 else ""),
        )
        
        # Get page summaries from parsed pages
        parsed_pages = document.metadata.get("parsed_pages", {})
        page_summaries = {
            page.page_number: parsed_pages.get(str(page.page_number), {}).get("page_summary")
            for page in document.pages
        }
        
        # Extract section headings for context
        section_headings = self._extract_section_headings(document)
        
        summaries: list[str] = []
        updated_pages = []
        total_chunks_enriched = 0
        
        for page in document.pages:
            page_summary = page_summaries.get(page.page_number)
            section_heading = section_headings.get(page.page_number)
            
            updated_chunks = []
            for chunk in page.chunks:
                # Enrich chunk with hierarchical context
                enriched_chunk = self._enrich_chunk_with_context(
                    chunk=chunk,
                    document_title=document.filename,
                    document_summary=document_summary,
                    page_summary=page_summary,
                    section_heading=section_heading,
                )
                updated_chunks.append(enriched_chunk)
                total_chunks_enriched += 1
                
                if enriched_chunk.metadata and enriched_chunk.metadata.summary:
                    summaries.append(enriched_chunk.metadata.summary)
            
            updated_page = page.model_copy(update={"chunks": updated_chunks})
            updated_pages.append(updated_page)
        
        updated_document = document.model_copy(
            update={
                "pages": updated_pages,
                "summary": document_summary,  # Now a real LLM-generated summary
                "status": "enriched",
            }
        )
        
        logger.info(
            "✅ Enrichment complete: %d chunks enriched with contextualized text",
            total_chunks_enriched,
        )
        
        self.observability.record_event(
            stage="enrichment",
            details={
                "document_id": updated_document.id,
                "chunk_count": total_chunks_enriched,
                "has_document_summary": bool(document_summary),
            },
        )
        return updated_document

    def _summarize_chunk(self, text: str) -> str:
        if not text:
            return ""
        if self.summary_generator:
            return self.summary_generator.summarize(text)
        return text[:120].strip()
    
    def _generate_document_summary(self, document: Document) -> str:
        """Generate comprehensive document-level summary."""
        if not self.summary_generator or not self.use_llm_summarization:
            # Fallback: concatenate page summaries
            parsed_pages = document.metadata.get("parsed_pages", {})
            page_summaries = []
            for page_num in range(1, len(document.pages) + 1):
                parsed_page = parsed_pages.get(str(page_num))
                if parsed_page and parsed_page.get("page_summary"):
                    page_summaries.append(f"Page {page_num}: {parsed_page['page_summary']}")
            return " ".join(page_summaries)[:500]
        
        # Use LLM to generate document summary from page summaries
        parsed_pages = document.metadata.get("parsed_pages", {})
        content = []
        
        for page in document.pages:
            page_data = parsed_pages.get(str(page.page_number), {})
            if page_summary := page_data.get("page_summary"):
                content.append(f"**Page {page.page_number}**: {page_summary}")
            else:
                # Fallback to first 300 chars of cleaned text
                preview = (page.cleaned_text or page.text)[:300]
                content.append(f"**Page {page.page_number}**: {preview}...")
        
        context = "\n\n".join(content)
        
        prompt = f"""Document: {document.filename}
File Type: {document.file_type}
Total Pages: {len(document.pages)}

Page Summaries:
{context}

Generate a comprehensive 3-4 sentence summary of this entire document. Focus on:
1. Document type and purpose
2. Main topics covered
3. Key entities or standards mentioned
4. Overall scope and audience

Summary:"""
        
        try:
            summary = self.summary_generator.summarize(prompt)
            logger.debug("Generated document summary via LLM: %s", summary[:100])
            return summary
        except Exception as exc:
            logger.warning("Failed to generate document summary via LLM: %s", exc)
            # Fallback to page summary concatenation
            return " ".join(content)[:500]
    
    def _extract_section_headings(self, document: Document) -> dict[int, str | None]:
        """Extract section headings for each page."""
        parsed_pages = document.metadata.get("parsed_pages", {})
        headings = {}
        current_heading = None
        
        for page in document.pages:
            parsed_page = parsed_pages.get(str(page.page_number))
            if not parsed_page:
                headings[page.page_number] = current_heading
                continue
            
            # Find first heading component on page
            for component in parsed_page.get("components", []):
                if component.get("type") == "text" and component.get("text_type") == "heading":
                    current_heading = component.get("text")
                    break
            
            headings[page.page_number] = current_heading
        
        return headings
    
    def _enrich_chunk_with_context(
        self,
        chunk: Any,
        document_title: str,
        document_summary: str,
        page_summary: str | None,
        section_heading: str | None,
    ) -> Any:
        """Enrich chunk with summaries and generate contextualized text."""
        from ..domain.models import Chunk, Metadata
        
        # Generate chunk summary if missing
        chunk_summary = chunk.metadata.summary if chunk.metadata else None
        if not chunk_summary and self.summary_generator and self.use_llm_summarization:
            # Pass hierarchical context to summary generation
            summary_prompt = f"""Document: {document_title}
Document Summary: {document_summary}
Page {chunk.page_number} Summary: {page_summary or 'N/A'}
Component Type: {chunk.metadata.component_type if chunk.metadata else 'text'}

Chunk Text:
{chunk.cleaned_text or chunk.text}

Generate a 2-sentence summary of this chunk, explaining what information it contains and how it relates to the document's overall purpose.

Summary:"""
            try:
                chunk_summary = self.summary_generator.summarize(summary_prompt)
                logger.debug("Generated chunk summary via LLM")
            except Exception as exc:
                logger.warning("Failed to generate chunk summary: %s", exc)
                chunk_summary = (chunk.cleaned_text or chunk.text)[:120].strip()
        
        # Build contextualized text for embedding (Anthropic pattern)
        context_parts = [
            f"Document: {document_title}",
            f"Page: {chunk.page_number}",
        ]
        
        if section_heading:
            context_parts.append(f"Section: {section_heading}")
        
        if chunk.metadata:
            if chunk.metadata.component_type:
                context_parts.append(f"Type: {chunk.metadata.component_type}")
            if chunk.metadata.component_description:
                context_parts.append(f"Description: {chunk.metadata.component_description[:100]}")
            if chunk.metadata.component_summary:
                context_parts.append(f"Table Summary: {chunk.metadata.component_summary[:100]}")
        
        context_prefix = " | ".join(context_parts)
        contextualized_text = f"[{context_prefix}]\n\n{chunk.cleaned_text or chunk.text}"
        
        # Update metadata
        if chunk.metadata:
            updated_metadata = chunk.metadata.model_copy(update={
                "summary": chunk_summary,
                "document_title": document_title,
                "document_summary": document_summary,
                "page_summary": page_summary,
                "section_heading": section_heading,
            })
        else:
            updated_metadata = Metadata(
                document_id=chunk.document_id,
                page_number=chunk.page_number,
                chunk_id=chunk.id,
                start_offset=chunk.start_offset,
                end_offset=chunk.end_offset,
                summary=chunk_summary,
                document_title=document_title,
                document_summary=document_summary,
                page_summary=page_summary,
                section_heading=section_heading,
            )
        
        logger.debug(
            "🎯 Enriched chunk (page=%d, type=%s) with contextualized text",
            chunk.page_number,
            updated_metadata.component_type or "text",
        )
        
        return chunk.model_copy(update={
            "metadata": updated_metadata,
            "contextualized_text": contextualized_text,
        })
