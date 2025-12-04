"""Parallel page processing service for parsing and cleaning stages."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from ..domain.models import Document, Page
from ..parsing.parallel_pixmap_factory import ParallelPixmapFactory, PixmapInfo
from ..parsing.schemas import CleanedPage, ParsedPage
from .rate_limiter import RateLimiter

if TYPE_CHECKING:
    from .parsing_service import ParsingService
    from .cleaning_service import CleaningService

logger = logging.getLogger(__name__)


class ParallelPageProcessor:
    """Coordinates parallel processing of pages during parsing and cleaning.
    
    This service wraps existing ParsingService and CleaningService with
    parallel execution capabilities:
    
    1. Pixmap generation: Uses process pool (CPU-bound, 3-5x speedup)
    2. LLM parsing/cleaning: Uses asyncio (I/O-bound, concurrent API calls)
    3. Rate limiting: Respects API rate limits across parallel operations
    
    The service maintains immutability by returning new Document instances
    and does not mutate any input documents.
    """

    def __init__(
        self,
        parsing_service: ParsingService,
        cleaning_service: CleaningService,
        parallel_pixmap_factory: ParallelPixmapFactory | None = None,
        rate_limiter: RateLimiter | None = None,
        max_workers: int = 4,
        enable_page_parallelism: bool = True,
    ) -> None:
        """Initialize the parallel page processor.
        
        Args:
            parsing_service: Service for parsing individual pages
            cleaning_service: Service for cleaning individual pages
            parallel_pixmap_factory: Factory for parallel pixmap generation
            rate_limiter: Rate limiter for API calls (optional)
            max_workers: Maximum concurrent page operations
            enable_page_parallelism: Enable/disable parallel processing (for testing)
        """
        self.parsing = parsing_service
        self.cleaning = cleaning_service
        self.pixmap_factory = parallel_pixmap_factory
        self.rate_limiter = rate_limiter
        self.max_workers = max_workers
        self.enable = enable_page_parallelism

    async def parse_pages_parallel(
        self,
        document: Document,
        file_bytes: bytes,
        doc_logger=None,
    ) -> Document:
        """Parse all pages in parallel with parallel pixmap generation.
        
        Strategy:
        1. Generate all pixmaps in parallel (biggest bottleneck, process pool)
        2. Parse pages in parallel using LLM vision (I/O-bound, asyncio)
        3. Combine results into updated document
        
        Args:
            document: Document to parse
            file_bytes: Raw file bytes for pixmap generation
            doc_logger: Optional batch logger for clean progress logging
            
        Returns:
            New Document instance with parsed pages
        """
        if not self.enable:
            # Fall back to sequential processing
            return self.parsing.parse(document, file_bytes=file_bytes)

        # Step 1: Generate all pixmaps in parallel (if enabled)
        pixmap_map: dict[int, PixmapInfo] = {}
        if self.pixmap_factory and self.parsing.include_images:
            try:
                pixmap_map = await self.pixmap_factory.generate_async(
                    document.id,
                    file_bytes,
                    doc_logger=doc_logger,  # Pass logger for per-page progress
                    filename=document.filename,  # Pass filename for logging
                )
                
                if doc_logger:
                    doc_logger.record_event("pixmap_generation", {
                        "document_id": document.id,
                        "filename": document.filename,
                        "total_generated": len(pixmap_map),
                        "page_count": len(document.pages) if document.pages else 0,
                    })
            except Exception as exc:
                if doc_logger:
                    doc_logger.record_event("pixmap_generation_failed", {
                        "document_id": document.id,
                        "filename": document.filename,
                        "error": str(exc),
                    })
                logger.warning(
                    "Parallel pixmap generation failed, falling back to sequential: %s",
                    exc,
                    exc_info=True,
                )
                # Fall back to sequential parsing
                return self.parsing.parse(document, file_bytes=file_bytes)

        # If no pages yet, need to extract page texts first
        if not document.pages:
            # Use sequential parsing to get page structure
            document = self.parsing.parse(document, file_bytes=file_bytes)
            return document

        # Step 2: Parse pages in parallel using asyncio
        updated_pages = []
        semaphore = asyncio.Semaphore(self.max_workers)

        async def parse_single_page(page: Page) -> Page:
            """Parse a single page with rate limiting."""
            async with semaphore:
                if self.rate_limiter:
                    await self.rate_limiter.acquire(1)

                # Get pixmap for this page if available
                pixmap_info = pixmap_map.get(page.page_number)
                pixmap_path = str(pixmap_info.path) if pixmap_info else None

                # Run the structured parser (blocking call)
                loop = asyncio.get_event_loop()
                parsed_page, latency = await loop.run_in_executor(
                    None,
                    self.parsing._run_structured_parser,
                    document.id,
                    page.page_number,
                    "" if pixmap_info else page.text,  # Empty text when using vision
                    pixmap_path,
                )

                # Update page metadata with parsed info
                updated_metadata = document.metadata.copy()
                parsed_pages_meta = updated_metadata.get("parsed_pages", {})
                parsed_pages_meta[str(page.page_number)] = parsed_page.model_dump()
                updated_metadata["parsed_pages"] = parsed_pages_meta

                return page

        # Parse all pages concurrently
        tasks = [parse_single_page(page) for page in document.pages]
        updated_pages = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions and log them
        final_pages = []
        for i, result in enumerate(updated_pages):
            if isinstance(result, Exception):
                logger.error(
                    "Failed to parse page %d: %s",
                    document.pages[i].page_number,
                    result,
                    exc_info=result,
                )
                # Keep original page on error
                final_pages.append(document.pages[i])
            else:
                final_pages.append(result)

        logger.info(
            "✅ Parallel page parsing complete: doc=%s, %d pages parsed",
            document.id,
            len(final_pages),
        )

        return document.model_copy(
            update={"pages": final_pages, "status": "parsed"}
        )

    async def clean_pages_parallel(
        self,
        document: Document,
        doc_logger=None,
    ) -> Document:
        """Clean all pages in parallel using LLM.
        
        Strategy:
        1. Clean each page independently using LLM
        2. Run cleaning operations concurrently with rate limiting
        3. Combine results into updated document
        
        Args:
            document: Document with pages to clean
            doc_logger: Optional batch logger for clean progress logging
            
        Returns:
            New Document instance with cleaned pages
        """
        if not self.enable or not document.pages:
            # Fall back to sequential processing
            return self.cleaning.clean(document)

        updated_pages = []
        updated_metadata = document.metadata.copy()
        updated_metadata["cleaning_metadata_by_page"] = {}

        semaphore = asyncio.Semaphore(self.max_workers)

        async def clean_single_page(page: Page) -> Page:
            """Clean a single page with rate limiting."""
            async with semaphore:
                if self.rate_limiter:
                    await self.rate_limiter.acquire(1)

                # Run the cleaning operation (blocking call)
                loop = asyncio.get_event_loop()
                
                # Apply normalizer to page text
                raw_text = page.text or ""
                cleaned_text = await loop.run_in_executor(
                    None,
                    self.cleaning.normalizer,
                    raw_text,
                )

                # If structured cleaner is available, use it
                if self.cleaning.structured_cleaner:
                    parsed_pages_meta = document.metadata.get("parsed_pages", {})
                    parsed_payload = parsed_pages_meta.get(
                        str(page.page_number)
                    ) or parsed_pages_meta.get(page.page_number)
                    
                    if parsed_payload:
                        parsed_page = ParsedPage.model_validate(parsed_payload)
                        pixmap_path = parsed_pages_meta.get("pixmap_assets", {}).get(
                            str(page.page_number)
                        )
                        
                        cleaned_segments = await loop.run_in_executor(
                            None,
                            self.cleaning._run_structured_cleaner,
                            parsed_page,
                            pixmap_path,
                        )
                        
                        cleaned_text = "\n\n".join(
                            segment.text for segment in cleaned_segments.segments
                        ).strip() or cleaned_text

                # Log per-page progress (clean minimal format)
                if doc_logger:
                    doc_logger.record_event("cleaning_page_complete", {
                        "document_id": document.id,
                        "filename": document.filename,
                        "page_number": page.page_number,
                        "page_count": len(document.pages),
                        "cleaned_tokens": len(cleaned_text.split()),
                    })

                return page.model_copy(update={"cleaned_text": cleaned_text})

        # Clean all pages concurrently
        tasks = [clean_single_page(page) for page in document.pages]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions and log them
        final_pages = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    "Failed to clean page %d: %s",
                    document.pages[i].page_number,
                    result,
                    exc_info=result,
                )
                # Keep original page on error
                final_pages.append(document.pages[i])
            else:
                final_pages.append(result)

        logger.info(
            "✅ Parallel page cleaning complete: doc=%s, %d pages cleaned",
            document.id,
            len(final_pages),
        )

        return document.model_copy(
            update={
                "pages": final_pages,
                "status": "cleaned",
                "metadata": updated_metadata,
            }
        )

