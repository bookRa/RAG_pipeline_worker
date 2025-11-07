from pathlib import Path
import re
import time

from fastapi.testclient import TestClient

from src.app.main import app


client = TestClient(app)


def test_dashboard_page_loads():
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "Manual test harness" in response.text


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
    for _ in range(10):
        fragment = client.get(f"/dashboard/runs/{run_id}/fragment")
        assert fragment.status_code == 200
        if 'data-run-status="completed"' in fragment.text:
            assert "Stage breakdown" in fragment.text
            assert "chunking" in fragment.text
            assert "cleaning" in fragment.text
            assert "vectorization" in fragment.text
            completed = True
            break
        time.sleep(0.01)

    assert completed, "pipeline run did not complete in time"
