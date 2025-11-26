from src.app.domain.models import Document, Page, Chunk, Metadata
from src.app.persistence.adapters.document_filesystem import FileSystemDocumentRepository


def _seed_document_with_flagged_segment(tmp_path):
    repository = FileSystemDocumentRepository(tmp_path)
    document = Document(filename="a.pdf", file_type="pdf")
    
    segment = {
        "segment_id": "seg-123",
        "text": "Replace gasket seal - contains phone number 555-1234",
        "needs_review": True,
        "rationale": "Contains contact information that must be verified",
    }
    
    cleaning_metadata = {
        1: {
            "profile": "default",
            "llm_segments": {
                "segments": [segment.copy()],
            },
        }
    }
    
    chunk_id = "chunk-1"
    chunk_metadata = Metadata(
        document_id=document.id,
        page_number=1,
        chunk_id=chunk_id,
        start_offset=0,
        end_offset=len(segment["text"]),
        title="a.pdf-p1-c0",
        extra={
            "cleaning": {
                "segment_id": chunk_id,
                "llm_segments": {
                    "segments": [segment.copy()],
                },
            }
        },
    )
    
    chunk = Chunk(
        id=chunk_id,
        document_id=document.id,
        page_number=1,
        text=segment["text"],
        start_offset=0,
        end_offset=len(segment["text"]),
        cleaned_text=segment["text"],
        metadata=chunk_metadata,
    )
    page = Page(
        document_id=document.id,
        page_number=1,
        text=segment["text"],
        cleaned_text=segment["text"],
        chunks=[chunk],
    )
    
    document = document.model_copy(
        update={
            "pages": [page],
            "metadata": {
                "cleaning_metadata_by_page": cleaning_metadata,
            },
        }
    )
    repository.save(document)
    return repository, document.id, segment["segment_id"]


def test_document_repository_persists_and_lists(tmp_path):
    repository = FileSystemDocumentRepository(tmp_path)
    doc_a = Document(filename="a.pdf", file_type="pdf")
    doc_b = Document(filename="b.docx", file_type="docx")

    repository.save(doc_a)
    repository.save(doc_b)

    stored = repository.list()
    stored_ids = {doc.id for doc in stored}
    assert doc_a.id in stored_ids
    assert doc_b.id in stored_ids

    fetched = repository.get(doc_a.id)
    assert fetched is not None
    assert fetched.filename == "a.pdf"


def test_approve_segment_updates_metadata(tmp_path):
    repository, document_id, segment_id = _seed_document_with_flagged_segment(tmp_path)
    
    updated = repository.approve_segment(document_id, segment_id)
    assert updated is True
    
    document = repository.get(document_id)
    assert document is not None
    cleaning_metadata = document.metadata["cleaning_metadata_by_page"]
    page_meta = cleaning_metadata["1"]
    flagged_segment = page_meta["llm_segments"]["segments"][0]
    assert flagged_segment["needs_review"] is False
    assert flagged_segment["review_history"][-1]["action"] == "approved"


def test_edit_segment_updates_text_and_page(tmp_path):
    repository, document_id, segment_id = _seed_document_with_flagged_segment(tmp_path)
    corrected_text = "Replace gasket seal (contact: ops@contoso.com)"
    
    updated = repository.edit_segment(document_id, segment_id, corrected_text)
    assert updated is True
    
    document = repository.get(document_id)
    assert document is not None
    cleaning_metadata = document.metadata["cleaning_metadata_by_page"]
    page_meta = cleaning_metadata["1"]
    flagged_segment = page_meta["llm_segments"]["segments"][0]
    assert flagged_segment["text"] == corrected_text
    assert flagged_segment["needs_review"] is False
    history_entry = flagged_segment["review_history"][-1]
    assert history_entry["action"] == "edited"
    assert history_entry["corrected_text"] == corrected_text
    
    page = document.pages[0]
    assert page.cleaned_text == corrected_text
