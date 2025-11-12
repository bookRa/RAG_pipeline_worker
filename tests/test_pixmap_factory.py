from pathlib import Path

import pytest

from src.app.parsing.pixmap_factory import PixmapFactory


def test_pixmap_factory_renders_pdf(tmp_path):
    pdf_path = Path(__file__).parent / "doc_short_clean.pdf"
    if not pdf_path.exists():
        pytest.skip("Sample PDF not available for pixmap test")

    factory = PixmapFactory(tmp_path, dpi=300)
    result = factory.generate("doc123", pdf_path.read_bytes())

    assert result
    first_page = result[min(result.keys())]
    assert first_page.path.exists()
    assert first_page.size_bytes > 0
