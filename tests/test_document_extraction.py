import pytest

from app.services.document_extraction import validate_pdf_signature, _needs_ocr


def test_validate_pdf_signature_valid():
    assert validate_pdf_signature(b"%PDF-1.4 rest") is True


def test_validate_pdf_signature_invalid():
    assert validate_pdf_signature(b"not a pdf") is False
    assert validate_pdf_signature(b"") is False


def test_needs_ocr_threshold():
    assert _needs_ocr("short") is True
    assert _needs_ocr("x" * 100) is False
