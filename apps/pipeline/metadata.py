from __future__ import annotations

from datetime import date, datetime
from urllib.parse import urlparse

import pymupdf
from django.utils import timezone


def _parse_date(value: date | datetime | str | None, field: str, errors: list[str]) -> date | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        errors.append(f"{field}: wajib diisi.")
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        errors.append(f"{field}: format tidak valid (pakai YYYY-MM-DD).")
        return None


def _is_valid_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def validate_metadata(
    *,
    title: str,
    publisher: str,
    publication_date: date | datetime | str | None,
    period_start: date | datetime | str | None,
    period_end: date | datetime | str | None,
    source_url: str = "",
    notes: str = "",
) -> list[str]:
    errors: list[str] = []

    if not title.strip():
        errors.append("title: wajib diisi.")
    if not publisher.strip():
        errors.append("publisher: wajib diisi.")

    pub_date = _parse_date(publication_date, "publication_date", errors)
    start_date = _parse_date(period_start, "period_start", errors)
    end_date = _parse_date(period_end, "period_end", errors)

    if pub_date is not None and pub_date > timezone.localdate():
        errors.append("publication_date: tidak boleh di masa depan.")
    if start_date is not None and end_date is not None and start_date > end_date:
        errors.append("period_start: harus lebih kecil atau sama dengan period_end.")

    if source_url.strip() and not _is_valid_url(source_url):
        errors.append("source_url: format URL tidak valid.")

    return errors


def validate_file(
    *,
    filename: str,
    size_bytes: int,
    header: bytes,
    page_count: int | None,
    max_upload_mb: int,
    max_pages: int,
) -> list[str]:
    errors: list[str] = []

    if not filename.lower().endswith(".pdf"):
        errors.append("file: ekstensi harus .pdf.")
    if not header.startswith(b"%PDF"):
        errors.append("file: berkas bukan PDF yang valid.")
    max_bytes = max_upload_mb * 1024 * 1024
    if size_bytes > max_bytes:
        errors.append(f"file: ukuran melebihi {max_upload_mb} MB.")
    if page_count is not None and page_count > max_pages:
        errors.append(f"file: jumlah halaman melebihi {max_pages}.")

    return errors


def count_pdf_pages(data: bytes) -> int:
    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            return doc.page_count
    except Exception as exc:
        raise ValueError("PDF tidak dapat dibuka.") from exc
