from pathlib import Path

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
    assert "Stage breakdown" in response.text
    assert "chunking" in response.text
    assert "cleaning" in response.text
    assert "vectorization" in response.text
