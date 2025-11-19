from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile

from ..application.use_cases import GetDocumentUseCase, ListDocumentsUseCase, UploadDocumentUseCase
from ..container import get_app_container

router = APIRouter()


def get_upload_use_case() -> UploadDocumentUseCase:
    return get_app_container().upload_document_use_case


def get_list_use_case() -> ListDocumentsUseCase:
    return get_app_container().list_documents_use_case


def get_get_use_case() -> GetDocumentUseCase:
    return get_app_container().get_document_use_case


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    use_case: UploadDocumentUseCase = Depends(get_upload_use_case),
) -> dict:
    file_bytes = await file.read()
    document = use_case.execute(
        filename=file.filename or "",
        file_type=file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else "",
        file_bytes=file_bytes,
        content_type=file.content_type,
    )
    return document.model_dump()


@router.get("/documents")
async def list_documents(
    use_case: ListDocumentsUseCase = Depends(get_list_use_case),
) -> list[dict]:
    documents = use_case.execute()
    return [doc.model_dump() for doc in documents]


@router.get("/documents/{doc_id}")
async def get_document(
    doc_id: str,
    use_case: GetDocumentUseCase = Depends(get_get_use_case),
) -> dict:
    document = use_case.execute(doc_id)
    return document.model_dump()


@router.get("/documents/{document_id}/segments-for-review")
async def get_segments_for_review(
    document_id: str,
    use_case: GetDocumentUseCase = Depends(get_get_use_case),
) -> dict:
    """Get all segments flagged for review from a document."""
    document = use_case.execute(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    flagged_segments = []
    
    # Extract segments from cleaning metadata
    cleaning_metadata = document.metadata.get("cleaning_metadata_by_page", {}) if document.metadata else {}
    
    for page in document.pages:
        page_meta = cleaning_metadata.get(page.page_number, {})
        llm_segments = page_meta.get("llm_segments", {})
        segments = llm_segments.get("segments", [])
        
        for segment in segments:
            if segment.get("needs_review"):
                # Find associated chunk if available
                chunk_id = None
                for chunk in page.chunks:
                    if chunk.metadata and chunk.metadata.extra:
                        cleaning_extra = chunk.metadata.extra.get("cleaning", {})
                        if cleaning_extra.get("llm_segments"):
                            segs = cleaning_extra["llm_segments"].get("segments", [])
                            if any(s.get("segment_id") == segment.get("segment_id") for s in segs):
                                chunk_id = chunk.id
                                break
                
                flagged_segments.append({
                    "document_id": document_id,
                    "page_number": page.page_number,
                    "chunk_id": chunk_id,
                    "segment_id": segment.get("segment_id"),
                    "text": segment.get("text", ""),
                    "rationale": segment.get("rationale"),
                })
    
    return {"flagged_segments": flagged_segments}


@router.post("/segments/{segment_id}/approve")
async def approve_segment(
    segment_id: str,
    document_id: str = Body(...),
    use_case: GetDocumentUseCase = Depends(get_get_use_case),
) -> dict:
    """Mark a segment as reviewed/approved."""
    document = use_case.execute(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    container = get_app_container()
    repository = container.document_repository
    
    # Update segment review status in document metadata
    updated = repository.approve_segment(document_id, segment_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Segment not found")
    
    return {"status": "approved", "segment_id": segment_id}


@router.put("/segments/{segment_id}/edit")
async def edit_segment(
    segment_id: str,
    document_id: str = Body(...),
    corrected_text: str = Body(...),
    use_case: GetDocumentUseCase = Depends(get_get_use_case),
) -> dict:
    """Update a segment with corrected text from human reviewer."""
    document = use_case.execute(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    container = get_app_container()
    repository = container.document_repository
    
    # Update segment text and mark as reviewed
    updated = repository.edit_segment(document_id, segment_id, corrected_text)
    if not updated:
        raise HTTPException(status_code=404, detail="Segment not found")
    
    return {"status": "edited", "segment_id": segment_id, "corrected_text": corrected_text}
