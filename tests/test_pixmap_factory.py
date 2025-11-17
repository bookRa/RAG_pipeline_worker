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


def test_pixmap_factory_resizes_large_images(tmp_path):
    """Test that large images are resized to respect max dimensions."""
    pdf_path = Path(__file__).parent / "doc_short_noisy.pdf"
    if not pdf_path.exists():
        pytest.skip("Sample PDF not available for pixmap test")

    # Create factory with resize constraints
    factory = PixmapFactory(tmp_path, dpi=300, max_width=2048, max_height=2048)
    result = factory.generate("doc_resize_test", pdf_path.read_bytes())

    assert result
    first_page = result[min(result.keys())]
    assert first_page.path.exists()

    # Verify the image was resized by checking dimensions
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("PIL not available")

    with Image.open(first_page.path) as img:
        width, height = img.size
        # Image should not exceed max dimensions
        assert width <= 2048, f"Width {width} exceeds max 2048"
        assert height <= 2048, f"Height {height} exceeds max 2048"
        # At least one dimension should be at the limit (since aspect ratio is preserved)
        assert width == 2048 or height == 2048, "Image should be resized to max dimension"


def test_pixmap_factory_preserves_small_images(tmp_path):
    """Test that small images are not resized when they're already below max dimensions."""
    pdf_path = Path(__file__).parent / "doc_short_clean.pdf"
    if not pdf_path.exists():
        pytest.skip("Sample PDF not available for pixmap test")

    # Create factory with very large max dimensions
    factory = PixmapFactory(tmp_path, dpi=150, max_width=5000, max_height=5000)
    result = factory.generate("doc_small_test", pdf_path.read_bytes())

    assert result
    first_page = result[min(result.keys())]
    assert first_page.path.exists()

    # Verify the image dimensions are smaller than max (not artificially enlarged)
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("PIL not available")

    with Image.open(first_page.path) as img:
        width, height = img.size
        # Should be well below the max since we're using lower DPI
        assert width < 5000
        assert height < 5000


def test_pixmap_resizing_maintains_aspect_ratio(tmp_path):
    """Test that resizing maintains the original aspect ratio."""
    pdf_path = Path(__file__).parent / "doc_short_noisy.pdf"
    if not pdf_path.exists():
        pytest.skip("Sample PDF not available for pixmap test")

    # First, get original dimensions without resizing
    factory_orig = PixmapFactory(tmp_path / "original", dpi=300)
    result_orig = factory_orig.generate("doc_orig", pdf_path.read_bytes())
    first_page_orig = result_orig[min(result_orig.keys())]

    try:
        from PIL import Image
    except ImportError:
        pytest.skip("PIL not available")

    with Image.open(first_page_orig.path) as img_orig:
        orig_width, orig_height = img_orig.size
        orig_aspect_ratio = orig_width / orig_height

    # Now resize and check aspect ratio is maintained
    factory_resized = PixmapFactory(tmp_path / "resized", dpi=300, max_width=2048, max_height=2048)
    result_resized = factory_resized.generate("doc_resized", pdf_path.read_bytes())
    first_page_resized = result_resized[min(result_resized.keys())]

    with Image.open(first_page_resized.path) as img_resized:
        resized_width, resized_height = img_resized.size
        resized_aspect_ratio = resized_width / resized_height

    # Aspect ratios should match within a small tolerance (0.1%)
    aspect_ratio_diff = abs(orig_aspect_ratio - resized_aspect_ratio)
    tolerance = 0.001 * orig_aspect_ratio
    assert aspect_ratio_diff < tolerance, (
        f"Aspect ratio changed: original={orig_aspect_ratio:.4f}, "
        f"resized={resized_aspect_ratio:.4f}"
    )


def test_pixmap_factory_no_resize_when_not_configured(tmp_path):
    """Test that images are not resized when max dimensions are not set."""
    pdf_path = Path(__file__).parent / "doc_short_noisy.pdf"
    if not pdf_path.exists():
        pytest.skip("Sample PDF not available for pixmap test")

    # Create factory without resize constraints
    factory_no_resize = PixmapFactory(tmp_path / "no_resize", dpi=300)
    result_no_resize = factory_no_resize.generate("doc_no_resize", pdf_path.read_bytes())

    # Create factory with resize constraints
    factory_with_resize = PixmapFactory(
        tmp_path / "with_resize", dpi=300, max_width=2048, max_height=2048
    )
    result_with_resize = factory_with_resize.generate("doc_with_resize", pdf_path.read_bytes())

    try:
        from PIL import Image
    except ImportError:
        pytest.skip("PIL not available")

    # Get dimensions from both
    with Image.open(result_no_resize[1].path) as img_no_resize:
        width_no_resize, height_no_resize = img_no_resize.size

    with Image.open(result_with_resize[1].path) as img_with_resize:
        width_with_resize, height_with_resize = img_with_resize.size

    # No-resize version should be larger
    assert width_no_resize > width_with_resize
    assert height_no_resize > height_with_resize
