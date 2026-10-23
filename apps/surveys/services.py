from __future__ import annotations

from typing import Any

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import UploadedFile

from apps.pipeline.metadata import count_pdf_pages, validate_file, validate_metadata
from apps.surveys.models import Survey
from apps.surveys.storage import compute_sha256


def _build_survey_fields(cleaned_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": str(cleaned_data.get("title") or "").strip(),
        "publisher": str(cleaned_data.get("publisher") or "").strip(),
        "publication_date": cleaned_data.get("publication_date"),
        "period_start": cleaned_data.get("period_start"),
        "period_end": cleaned_data.get("period_end"),
        "source_url": str(cleaned_data.get("source_url") or "").strip(),
        "notes": str(cleaned_data.get("notes") or "").strip(),
    }


def create_or_get_survey(
    *,
    cleaned_data: dict[str, Any],
    uploaded_file: UploadedFile,
    user: User | None = None,
) -> tuple[Survey, bool]:
    data = uploaded_file.read()
    sha256 = compute_sha256(data)

    existing = Survey.objects.filter(file_sha256=sha256).first()
    if existing is not None:
        return existing, False

    meta_errors = validate_metadata(
        title=str(cleaned_data.get("title") or ""),
        publisher=str(cleaned_data.get("publisher") or ""),
        publication_date=cleaned_data.get("publication_date"),
        period_start=cleaned_data.get("period_start"),
        period_end=cleaned_data.get("period_end"),
        source_url=str(cleaned_data.get("source_url") or ""),
        notes=str(cleaned_data.get("notes") or ""),
    )

    file_errors = validate_file(
        filename=uploaded_file.name or "",
        size_bytes=len(data),
        header=data[:1024],
        page_count=None,
        max_upload_mb=settings.MAX_UPLOAD_MB,
        max_pages=settings.MAX_PAGES,
    )
    page_count: int | None = None
    if not file_errors:
        try:
            page_count = count_pdf_pages(data)
        except ValueError:
            file_errors.append("file: PDF tidak dapat dibuka.")
        else:
            if page_count > settings.MAX_PAGES:
                file_errors.append(f"file: jumlah halaman melebihi {settings.MAX_PAGES}.")

    base_fields = _build_survey_fields(cleaned_data)

    if file_errors:
        survey = Survey.objects.create(
            **base_fields,
            file_sha256=sha256,
            page_count=page_count,
            status=Survey.Status.REJECTED_FILE,
            error_stage="file",
            error_reason="\n".join(file_errors),
            uploaded_by=user,
        )
        return survey, True

    if meta_errors:
        survey = Survey.objects.create(
            **base_fields,
            file_sha256=sha256,
            page_count=page_count,
            status=Survey.Status.REJECTED_METADATA,
            error_stage="metadata",
            error_reason="\n".join(meta_errors),
            uploaded_by=user,
        )
        return survey, True

    uploaded_file.seek(0)
    survey = Survey.objects.create(
        **base_fields,
        file=uploaded_file,
        file_sha256=sha256,
        page_count=page_count,
        status=Survey.Status.PENDING,
        uploaded_by=user,
    )
    return survey, True
