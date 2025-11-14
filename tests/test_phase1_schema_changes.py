"""
Unit tests for Phase 1 schema enhancements.

Tests the new fields added to support:
- Table summarization
- Page summarization
- Component-aware metadata
- Hierarchical context
- Contextualized text for embedding
"""

from uuid import uuid4

import pytest

from src.app.domain.models import Chunk, Document, Metadata, Page
from src.app.parsing.schemas import (
    ParsedImageComponent,
    ParsedPage,
    ParsedTableComponent,
    ParsedTextComponent,
)


class TestParsedTableComponentEnhancements:
    """Test table_summary field in ParsedTableComponent."""

    def test_table_component_with_summary(self):
        """Test creating table component with summary."""
        table = ParsedTableComponent(
            order=1,
            caption="Revision History",
            rows=[
                {"REV": "A", "DESCRIPTION": "Initial Release", "DATE": "2024-01-01"},
                {"REV": "B", "DESCRIPTION": "Updated specs", "DATE": "2024-02-01"},
            ],
            table_summary="This table lists revision history for the drawing, showing revision letters, descriptions, and dates.",
        )

        assert table.type == "table"
        assert table.caption == "Revision History"
        assert len(table.rows) == 2
        assert table.table_summary is not None
        assert "revision history" in table.table_summary.lower()

    def test_table_component_without_summary(self):
        """Test that table_summary is optional."""
        table = ParsedTableComponent(
            order=1,
            caption="Parts List",
            rows=[{"PART": "A101", "QTY": "5"}],
        )

        assert table.type == "table"
        assert table.table_summary is None  # Should be optional


class TestParsedPageEnhancements:
    """Test page_summary field in ParsedPage."""

    def test_parsed_page_with_summary(self):
        """Test creating parsed page with summary."""
        page = ParsedPage(
            document_id=str(uuid4()),
            page_number=1,
            raw_text="# Introduction\n\nThis is the introduction page.",
            components=[
                ParsedTextComponent(order=1, text="Introduction", text_type="heading"),
                ParsedTextComponent(
                    order=2, text="This is the introduction page.", text_type="paragraph"
                ),
            ],
            page_summary="This page introduces the document and provides an overview of the content structure.",
        )

        assert page.page_number == 1
        assert page.page_summary is not None
        assert "introduces" in page.page_summary.lower()
        assert len(page.components) == 2

    def test_parsed_page_without_summary(self):
        """Test that page_summary is optional."""
        page = ParsedPage(
            document_id=str(uuid4()),
            page_number=2,
            raw_text="Some content",
            components=[],
        )

        assert page.page_number == 2
        assert page.page_summary is None  # Should be optional


class TestMetadataEnhancements:
    """Test component and hierarchical context fields in Metadata."""

    def test_metadata_with_component_context(self):
        """Test metadata with component context for images."""
        metadata = Metadata(
            document_id=str(uuid4()),
            page_number=1,
            chunk_id=str(uuid4()),
            start_offset=0,
            end_offset=100,
            component_id="comp-123",
            component_type="image",
            component_order=1,
            component_description="A technical drawing showing the assembly of part A101",
        )

        assert metadata.component_id == "comp-123"
        assert metadata.component_type == "image"
        assert metadata.component_order == 1
        assert metadata.component_description is not None
        assert metadata.component_summary is None  # Only for tables

    def test_metadata_with_table_context(self):
        """Test metadata with component context for tables."""
        metadata = Metadata(
            document_id=str(uuid4()),
            page_number=2,
            chunk_id=str(uuid4()),
            start_offset=0,
            end_offset=200,
            component_id="comp-456",
            component_type="table",
            component_order=2,
            component_summary="Parts list showing quantities and specifications for components A-F",
        )

        assert metadata.component_id == "comp-456"
        assert metadata.component_type == "table"
        assert metadata.component_order == 2
        assert metadata.component_summary is not None
        assert metadata.component_description is None  # Only for images

    def test_metadata_with_hierarchical_context(self):
        """Test metadata with full hierarchical context."""
        metadata = Metadata(
            document_id=str(uuid4()),
            page_number=3,
            chunk_id=str(uuid4()),
            start_offset=0,
            end_offset=150,
            document_title="Blueprint Reading Manual.pdf",
            document_summary="A comprehensive guide to reading and interpreting technical blueprints",
            page_summary="This page covers revision blocks and their importance in tracking changes",
            section_heading="Revision Control",
        )

        assert metadata.document_title == "Blueprint Reading Manual.pdf"
        assert metadata.document_summary is not None
        assert metadata.page_summary is not None
        assert metadata.section_heading == "Revision Control"

    def test_metadata_all_fields_optional(self):
        """Test that all new fields are optional."""
        metadata = Metadata(
            document_id=str(uuid4()),
            page_number=1,
            chunk_id=str(uuid4()),
            start_offset=0,
            end_offset=50,
        )

        # All component context fields should be None
        assert metadata.component_id is None
        assert metadata.component_type is None
        assert metadata.component_order is None
        assert metadata.component_description is None
        assert metadata.component_summary is None

        # All hierarchical context fields should be None
        assert metadata.document_title is None
        assert metadata.document_summary is None
        assert metadata.page_summary is None
        assert metadata.section_heading is None


class TestChunkEnhancements:
    """Test contextualized_text field in Chunk."""

    def test_chunk_with_contextualized_text(self):
        """Test creating chunk with contextualized text."""
        doc_id = str(uuid4())
        chunk = Chunk(
            id=str(uuid4()),
            document_id=doc_id,
            page_number=1,
            text="If a revision has been made, the revision block will be in the upper right corner.",
            start_offset=0,
            end_offset=79,
            cleaned_text="If a revision has been made, the revision block will be in the upper right corner.",
            contextualized_text="[Document: Blueprint Reading Manual | Page: 1 | Section: Revision Block | Type: text]\n\nIf a revision has been made, the revision block will be in the upper right corner.",
        )

        assert chunk.text is not None
        assert chunk.cleaned_text is not None
        assert chunk.contextualized_text is not None
        assert chunk.contextualized_text.startswith("[Document:")
        assert "Blueprint Reading Manual" in chunk.contextualized_text
        assert "Revision Block" in chunk.contextualized_text

    def test_chunk_without_contextualized_text(self):
        """Test that contextualized_text is optional."""
        doc_id = str(uuid4())
        chunk = Chunk(
            id=str(uuid4()),
            document_id=doc_id,
            page_number=1,
            text="Some text content",
            start_offset=0,
            end_offset=17,
        )

        assert chunk.text == "Some text content"
        assert chunk.contextualized_text is None  # Should be optional

    def test_chunk_with_all_text_variants(self):
        """Test chunk with raw, cleaned, and contextualized text."""
        doc_id = str(uuid4())
        metadata = Metadata(
            document_id=doc_id,
            page_number=2,
            chunk_id=str(uuid4()),
            start_offset=0,
            end_offset=50,
            component_type="table",
            component_summary="Parts list",
        )

        chunk = Chunk(
            id=str(uuid4()),
            document_id=doc_id,
            page_number=2,
            text="PART  | QTY  \nA101  | 5    ",  # Raw with extra spaces
            start_offset=0,
            end_offset=28,
            cleaned_text="PART | QTY\nA101 | 5",  # Cleaned
            contextualized_text="[Document: Manual | Page: 2 | Type: table]\n\nPART | QTY\nA101 | 5",
            metadata=metadata,
        )

        # All three text variants should exist and be different
        assert chunk.text != chunk.cleaned_text
        assert chunk.cleaned_text != chunk.contextualized_text
        assert "[Document:" in chunk.contextualized_text
        assert chunk.metadata.component_type == "table"
        assert chunk.metadata.component_summary == "Parts list"


class TestDocumentHelperMethods:
    """Test new helper methods in Document."""

    def test_replace_page(self):
        """Test replace_page helper method."""
        doc_id = str(uuid4())
        page1 = Page(
            document_id=doc_id, page_number=1, text="Original page 1 content"
        )
        page2 = Page(
            document_id=doc_id, page_number=2, text="Original page 2 content"
        )

        doc = Document(
            id=doc_id,
            filename="test.pdf",
            file_type="pdf",
            pages=[page1, page2],
        )

        # Replace page 1
        new_page1 = Page(
            document_id=doc_id, page_number=1, text="Updated page 1 content"
        )
        updated_doc = doc.replace_page(1, new_page1)

        assert len(updated_doc.pages) == 2
        assert updated_doc.pages[0].text == "Updated page 1 content"
        assert updated_doc.pages[1].text == "Original page 2 content"

        # Original document should be unchanged (immutability)
        assert doc.pages[0].text == "Original page 1 content"


class TestIntegrationScenarios:
    """Test integration scenarios combining multiple enhancements."""

    def test_full_hierarchical_context_flow(self):
        """Test a complete flow with all hierarchical context."""
        doc_id = str(uuid4())

        # Create a parsed page with table that has summary
        table = ParsedTableComponent(
            order=2,
            caption="Revision History",
            rows=[{"REV": "A", "DESC": "Initial"}],
            table_summary="This table tracks all revisions made to the drawing.",
        )

        parsed_page = ParsedPage(
            document_id=doc_id,
            page_number=2,
            raw_text="# Revisions\n[table]",
            components=[
                ParsedTextComponent(order=1, text="Revisions", text_type="heading"),
                table,
            ],
            page_summary="This page provides a history of all document revisions.",
        )

        # Create chunk with full context
        metadata = Metadata(
            document_id=doc_id,
            page_number=2,
            chunk_id=str(uuid4()),
            start_offset=0,
            end_offset=100,
            component_id=table.id,
            component_type="table",
            component_order=2,
            component_summary=table.table_summary,
            document_title="Blueprint ABC-123.pdf",
            document_summary="Technical blueprint for assembly ABC-123",
            page_summary=parsed_page.page_summary,
            section_heading="Revisions",
        )

        chunk = Chunk(
            id=str(uuid4()),
            document_id=doc_id,
            page_number=2,
            text="REV | DESC\nA | Initial",
            start_offset=0,
            end_offset=22,
            cleaned_text="REV | DESC\nA | Initial",
            contextualized_text="[Document: Blueprint ABC-123.pdf | Page: 2 | Section: Revisions | Type: table]\n\nREV | DESC\nA | Initial",
            metadata=metadata,
        )

        # Verify all context is preserved
        assert chunk.metadata.document_title == "Blueprint ABC-123.pdf"
        assert chunk.metadata.page_summary is not None
        assert chunk.metadata.section_heading == "Revisions"
        assert chunk.metadata.component_type == "table"
        assert chunk.metadata.component_summary is not None
        assert "Blueprint ABC-123.pdf" in chunk.contextualized_text
        assert "Section: Revisions" in chunk.contextualized_text

    def test_image_component_with_description_in_chunk(self):
        """Test image component flow with description in chunk metadata."""
        doc_id = str(uuid4())

        image = ParsedImageComponent(
            order=1,
            description="A circular emblem featuring a ship's wheel and an eagle",
            recognized_text="SWOS",
        )

        metadata = Metadata(
            document_id=doc_id,
            page_number=1,
            chunk_id=str(uuid4()),
            start_offset=0,
            end_offset=0,
            component_id=image.id,
            component_type="image",
            component_order=1,
            component_description=image.description,
        )

        chunk = Chunk(
            id=str(uuid4()),
            document_id=doc_id,
            page_number=1,
            text=image.description,
            start_offset=0,
            end_offset=len(image.description),
            cleaned_text=image.description,
            contextualized_text=f"[Document: Manual.pdf | Page: 1 | Type: image]\n\n{image.description}",
            metadata=metadata,
        )

        assert chunk.metadata.component_type == "image"
        assert chunk.metadata.component_description == image.description
        assert "ship's wheel" in chunk.metadata.component_description
        assert "Type: image" in chunk.contextualized_text

