import os
from pathlib import Path
import re
import shutil
import time

TEST_ARTIFACTS_DIR = Path(__file__).resolve().parent / "tmp_artifacts"
TEST_ARTIFACTS_DIR.mkdir(exist_ok=True)
os.environ["RUN_ARTIFACTS_DIR"] = str(TEST_ARTIFACTS_DIR)
os.environ["INGESTION_STORAGE_DIR"] = str(TEST_ARTIFACTS_DIR / "ingestion")
os.environ["DOCUMENT_STORAGE_DIR"] = str(TEST_ARTIFACTS_DIR / "documents")
os.environ["LLM__PROVIDER"] = "mock"
os.environ["EMBEDDINGS__PROVIDER"] = "mock"
os.environ.setdefault("CHUNKING__INCLUDE_IMAGES", "false")


def _clear_artifacts() -> None:
    for child in TEST_ARTIFACTS_DIR.glob("*"):
        if child.is_file():
            child.unlink()
        else:
            shutil.rmtree(child)


def setup_function(_: object) -> None:
    _clear_artifacts()

from fastapi.testclient import TestClient

from src.app.main import app
from src.app.container import get_app_container
from src.app.domain.models import Document, Page, Chunk, Metadata


client = TestClient(app)


def _create_document_with_flagged_segment() -> tuple[Document, str]:
    container = get_app_container()
    repository = container.document_repository
    
    document = Document(filename="review.pdf", file_type="pdf")
    segment = {
        "segment_id": "seg-review-1",
        "text": "Verify contact info for ACME (555-0100).",
        "needs_review": True,
        "rationale": "Contains contact information",
    }
    
    cleaning_metadata = {
        1: {
            "profile": "default",
            "llm_segments": {
                "segments": [segment.copy()],
            },
        }
    }
    
    chunk_id = "chunk-review-1"
    chunk_metadata = Metadata(
        document_id=document.id,
        page_number=1,
        chunk_id=chunk_id,
        start_offset=0,
        end_offset=len(segment["text"]),
        title="review.pdf-p1-c0",
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
    reloaded = repository.get(document.id)
    assert reloaded is not None
    return reloaded, segment["segment_id"]


def test_dashboard_page_loads():
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "Manual Test Harness" in response.text


def test_dashboard_upload_traces_pipeline():
    pdf_path = Path("tests/test_document.pdf")
    with pdf_path.open("rb") as pdf_file:
        response = client.post(
            "/dashboard/upload",
            files={"file": (pdf_path.name, pdf_file, "application/pdf")},
        )

    assert response.status_code == 200
    match = re.search(r'data-run-id="([^"]+)"', response.text)
    assert match, "run id not present in response"
    run_id = match.group(1)

    completed = False
    linked_document_id = None
    for _ in range(10):
        fragment = client.get(f"/dashboard/runs/{run_id}/fragment")
        assert fragment.status_code == 200
        if 'data-run-status="completed"' in fragment.text:
            assert "Detailed Stage Outputs" in fragment.text
            assert "chunking" in fragment.text
            assert "cleaning" in fragment.text
            assert "vectorization" in fragment.text
            container = get_app_container()
            run_record = container.pipeline_run_manager.get_run(run_id)
            assert run_record and run_record.document
            linked_document_id = run_record.document.id
            assert f'/dashboard/review?document_id={linked_document_id}' in fragment.text
            completed = True
            break
        time.sleep(0.01)

    assert completed, "pipeline run did not complete in time"
    assert linked_document_id is not None
    
    dashboard_page = client.get("/dashboard")
    assert dashboard_page.status_code == 200
    assert f'/dashboard/review?document_id={linked_document_id}' in dashboard_page.text


def test_review_page_loads():
    response = client.get("/dashboard/review")
    assert response.status_code == 200
    assert "Segments Requiring Review" in response.text


def test_segments_review_endpoints_flow():
    document, segment_id = _create_document_with_flagged_segment()
    
    response = client.get(f"/documents/{document.id}/segments-for-review")
    assert response.status_code == 200
    data = response.json()
    assert data["flagged_segments"]
    assert data["flagged_segments"][0]["segment_id"] == segment_id
    
    approve = client.post(
        f"/segments/{segment_id}/approve",
        json={"document_id": document.id},
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"
    
    response_after = client.get(f"/documents/{document.id}/segments-for-review")
    assert response_after.status_code == 200
    assert response_after.json()["flagged_segments"] == []
    
    document2, segment_id2 = _create_document_with_flagged_segment()
    corrected_text = "Updated contact info verified by QA."
    edit = client.put(
        f"/segments/{segment_id2}/edit",
        json={"document_id": document2.id, "corrected_text": corrected_text},
    )
    assert edit.status_code == 200
    payload = edit.json()
    assert payload["status"] == "edited"
    assert payload["corrected_text"] == corrected_text
    
    response_final = client.get(f"/documents/{document2.id}/segments-for-review")
    assert response_final.status_code == 200
    assert response_final.json()["flagged_segments"] == []
