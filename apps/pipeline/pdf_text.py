from __future__ import annotations

from typing import Iterable

import pymupdf
from django.conf import settings

from apps.surveys.models import PageText, Survey

SCAN_MESSAGE = "PDF tampaknya hasil scan/gambar. MVP belum mendukung OCR."
TOO_LONG_MESSAGE = "Dokumen terlalu panjang untuk MVP."


def extract_pages(data: bytes) -> list[tuple[int, str]]:
    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            return [(index + 1, page.get_text("text")) for index, page in enumerate(doc)]
    except Exception as exc:
        raise ValueError("PDF tidak dapat dibuka.") from exc


def format_pages_for_llm(pages: Iterable[tuple[int, str]]) -> str:
    return "\n\n".join(f"=== PAGE {page_no} ===\n{text}" for page_no, text in pages)


def check_text_limits(
    pages: list[tuple[int, str]],
    *,
    min_chars_per_page: int,
    max_text_chars: int,
) -> list[str]:
    if not pages:
        return ["PDF tidak berisi halaman."]

    total_chars = sum(len(text) for _, text in pages)
    errors: list[str] = []

    if total_chars > max_text_chars:
        errors.append(TOO_LONG_MESSAGE)

    avg_chars = total_chars / len(pages)
    if avg_chars < min_chars_per_page:
        errors.append(SCAN_MESSAGE)

    return errors


def _mark_rejected(survey: Survey, errors: list[str]) -> None:
    survey.status = Survey.Status.REJECTED_FILE
    survey.error_stage = "extraction"
    survey.error_reason = "\n".join(errors)
    survey.save(update_fields=["status", "error_stage", "error_reason"])


def extract_text_for_survey(survey: Survey) -> bool:
    if not survey.file:
        _mark_rejected(survey, ["Tidak ada berkas pada survei ini."])
        return False

    with survey.file.open("rb") as handle:
        data = handle.read()

    try:
        pages = extract_pages(data)
    except ValueError as exc:
        _mark_rejected(survey, [str(exc)])
        return False

    errors = check_text_limits(
        pages,
        min_chars_per_page=settings.MIN_CHARS_PER_PAGE,
        max_text_chars=settings.MAX_TEXT_CHARS,
    )
    if errors:
        _mark_rejected(survey, errors)
        return False

    PageText.objects.filter(survey=survey).delete()
    PageText.objects.bulk_create(
        [PageText(survey=survey, page_no=page_no, text=text) for page_no, text in pages]
    )
    return True


def format_survey_for_llm(survey: Survey) -> str:
    pages = list(
        survey.pages.order_by("page_no").values_list("page_no", "text")
    )
    return format_pages_for_llm(pages)
