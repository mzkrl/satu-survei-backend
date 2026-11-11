from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class PageExtraction:
    page_number: int
    text: str


@dataclass
class ExtractionResult:
    document_id: str | None
    metadata: dict[str, Any]
    pages: list[PageExtraction]
    tables: list[Any]
    full_text: str


PDF_SIGNATURE = b"%PDF"


def validate_pdf_signature(data: bytes) -> bool:
    return data.lstrip().startswith(PDF_SIGNATURE)


def _parse_pdf_date(raw: Any) -> date | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8", errors="ignore")
        except Exception:
            return None
    if not isinstance(raw, str):
        raw = str(raw)
    raw = raw.strip()
    if not raw:
        return None
    m = re.search(r"D:(\d{4})(\d{2})?(\d{2})?", raw)
    if not m:
        return None
    try:
        year = int(m.group(1))
        month = int(m.group(2) or 1)
        day = int(m.group(3) or 1)
        return date(year, month, day)
    except Exception:
        return None


def _extract_with_pypdf(data: bytes) -> tuple[list[PageExtraction], dict[str, Any]]:
    try:
        from pypdf import PdfReader
    except Exception as e:  # pragma: no cover
        raise RuntimeError("pypdf is required for PDF extraction") from e
    reader = PdfReader(io.BytesIO(data))
    meta = reader.metadata or {}
    metadata = {
        "title": getattr(meta, "title", None) or meta.get("/Title"),
        "publisher": getattr(meta, "producer", None) or meta.get("/Producer"),
        "publication_date": _parse_pdf_date(getattr(meta, "creation_date", None) or meta.get("/CreationDate")),
        "source_url": None,
    }
    pages: list[PageExtraction] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        pages.append(PageExtraction(page_number=i, text=text))
    return pages, metadata


def _ocr_page_image(image) -> str:
    try:
        import pytesseract
    except Exception:
        return ""
    try:
        return pytesseract.image_to_string(image) or ""
    except Exception:
        return ""


def _ocr_pdf(data: bytes) -> list[PageExtraction]:
    try:
        from pdf2image import convert_from_bytes
    except Exception:
        return []
    try:
        images = convert_from_bytes(data)
    except Exception:
        return []
    pages: list[PageExtraction] = []
    for i, img in enumerate(images, start=1):
        pages.append(PageExtraction(page_number=i, text=_ocr_page_image(img)))
    return pages


def _needs_ocr(text: str, min_chars: int = 40) -> bool:
    return len((text or "").strip()) < min_chars


def extract_document(data: bytes, document_id: str | None = None) -> ExtractionResult:
    pages, metadata = _extract_with_pypdf(data)
    # Per-page OCR fallback for scanned/low-text pages
    ocr_pages = None
    for idx, p in enumerate(pages):
        if _needs_ocr(p.text):
            if ocr_pages is None:
                ocr_pages = _ocr_pdf(data)
            if ocr_pages and idx < len(ocr_pages):
                ocr_text = ocr_pages[idx].text or ""
                if len(ocr_text.strip()) > len((p.text or "").strip()):
                    pages[idx] = PageExtraction(page_number=p.page_number, text=ocr_text)

    tables: list[Any] = []  # table extraction can be extended (e.g. camelot/pdfplumber)
    full_text = "\n\n".join(
        f"[Page {p.page_number}]\n{p.text}".strip() for p in pages if p.text
    )
    return ExtractionResult(
        document_id=document_id,
        metadata=metadata,
        pages=pages,
        tables=tables,
        full_text=full_text,
    )


def extraction_to_dict(result: ExtractionResult) -> dict[str, Any]:
    md = dict(result.metadata)
    if isinstance(md.get("publication_date"), date):
        md["publication_date"] = md["publication_date"].isoformat()
    return {
        "document_id": result.document_id,
        "metadata": md,
        "pages": [{"page_number": p.page_number, "text": p.text} for p in result.pages],
        "tables": result.tables,
    }
