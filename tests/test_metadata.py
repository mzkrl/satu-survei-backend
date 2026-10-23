from datetime import date, timedelta

from apps.pipeline.metadata import count_pdf_pages, validate_file, validate_metadata

TODAY = date.today()

VALID_META = {
    "title": "Survei Kepuasan Publik 2026",
    "publisher": "Lembaga Contoh",
    "publication_date": TODAY,
    "period_start": date(TODAY.year, 1, 1),
    "period_end": date(TODAY.year, 6, 30),
    "source_url": "https://contoh.or.id/laporan",
    "notes": "",
}


def test_valid_metadata_returns_no_errors() -> None:
    assert validate_metadata(**VALID_META) == []


def test_valid_metadata_accepts_iso_date_strings() -> None:
    meta = {
        **VALID_META,
        "publication_date": TODAY.isoformat(),
        "period_start": f"{TODAY.year}-01-01",
        "period_end": f"{TODAY.year}-06-30",
    }
    assert validate_metadata(**meta) == []


def test_missing_required_fields_returns_all_errors() -> None:
    errors = validate_metadata(
        title="",
        publisher="",
        publication_date=None,
        period_start=None,
        period_end=None,
    )
    fields = [e.split(":")[0] for e in errors]
    assert fields == ["title", "publisher", "publication_date", "period_start", "period_end"]


def test_invalid_date_format() -> None:
    errors = validate_metadata(**{**VALID_META, "publication_date": "32/13/2026"})
    assert any("publication_date" in e and "format" in e for e in errors)


def test_reversed_period() -> None:
    errors = validate_metadata(
        **{**VALID_META, "period_start": date(TODAY.year, 6, 1), "period_end": date(TODAY.year, 1, 1)}
    )
    assert any("period_start" in e for e in errors)


def test_future_publication_date() -> None:
    errors = validate_metadata(**{**VALID_META, "publication_date": TODAY + timedelta(days=1)})
    assert any("publication_date" in e and "masa depan" in e for e in errors)


def test_invalid_source_url() -> None:
    errors = validate_metadata(**{**VALID_META, "source_url": "bukan-url"})
    assert any("source_url" in e for e in errors)


def test_source_url_optional() -> None:
    assert validate_metadata(**{**VALID_META, "source_url": ""}) == []


def test_valid_pdf_file() -> None:
    errors = validate_file(
        filename="laporan.pdf",
        size_bytes=1000,
        header=b"%PDF-1.4\n...",
        page_count=10,
        max_upload_mb=15,
        max_pages=60,
    )
    assert errors == []


def test_non_pdf_extension() -> None:
    errors = validate_file(
        filename="laporan.txt",
        size_bytes=100,
        header=b"%PDF-1.4",
        page_count=1,
        max_upload_mb=15,
        max_pages=60,
    )
    assert any(".pdf" in e for e in errors)


def test_bad_magic_bytes() -> None:
    errors = validate_file(
        filename="laporan.pdf",
        size_bytes=100,
        header=b"PK\x03\x04not-a-pdf",
        page_count=1,
        max_upload_mb=15,
        max_pages=60,
    )
    assert any("PDF yang valid" in e for e in errors)


def test_too_large() -> None:
    errors = validate_file(
        filename="laporan.pdf",
        size_bytes=16 * 1024 * 1024,
        header=b"%PDF-1.4",
        page_count=1,
        max_upload_mb=15,
        max_pages=60,
    )
    assert any("ukuran" in e for e in errors)


def test_too_many_pages() -> None:
    errors = validate_file(
        filename="laporan.pdf",
        size_bytes=100,
        header=b"%PDF-1.4",
        page_count=61,
        max_upload_mb=15,
        max_pages=60,
    )
    assert any("halaman" in e for e in errors)


def test_count_pdf_pages(pdf_factory) -> None:
    assert count_pdf_pages(pdf_factory(pages=3)) == 3


def test_count_pdf_pages_rejects_garbage() -> None:
    try:
        count_pdf_pages(b"%PDF-1.4\nbukan pdf sungguhan")
    except ValueError as exc:
        assert "dibuka" in str(exc)
    else:
        raise AssertionError("expected ValueError")
