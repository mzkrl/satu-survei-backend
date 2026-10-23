from __future__ import annotations

import json
from datetime import date

import pymupdf
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.surveys.models import Survey
from apps.surveys.storage import compute_sha256

PROFILE_EXCERPT = (
    "Survei menggunakan multistage random sampling dengan sampel sebanyak "
    "1.200 responden, margin of error 2,9 persen pada tingkat kepercayaan 95 persen."
)
EVIDENCE_EXCERPT = "Kepuasan kinerja pemerintah sebesar 72,4 persen"
PAGE_ONE_TEXT = (
    "Laporan disusun oleh Lembaga X. Populasi: WNI usia 17+. "
    "Wilayah: Nasional. Metode: tatap muka. "
    f"{PROFILE_EXCERPT} {EVIDENCE_EXCERPT}."
)


def make_normalization_output(
    *,
    profile_excerpt: str = PROFILE_EXCERPT,
    evidence_excerpt: str = EVIDENCE_EXCERPT,
) -> dict:
    def found(value, excerpt: str = profile_excerpt) -> dict:
        return {"status": "found", "value": value, "source": {"page": 1, "excerpt": excerpt}}

    def unknown() -> dict:
        return {"status": "unknown", "value": None, "source": None}

    return {
        "survey_profile": {
            "sample_size": found(1200),
            "sampling_method": found("multistage random sampling"),
            "moe_claimed_pct": found(2.9),
            "confidence_level_pct": found(95),
            "fieldwork_start": unknown(),
            "fieldwork_end": unknown(),
            "sponsor_or_funder": unknown(),
            "conducted_by": found("Lembaga X", "Laporan disusun oleh Lembaga X"),
            "population": found("WNI usia 17+", "Populasi: WNI usia 17+"),
            "geography": found("Nasional", "Wilayah: Nasional"),
            "mode": found("tatap muka", "Metode: tatap muka"),
            "weighting": unknown(),
            "question_wording_disclosed": unknown(),
        },
        "evidence_records": [
            {
                "id": "E1",
                "label_original": "Kepuasan kinerja pemerintah",
                "label_normalized": "Kepuasan kinerja pemerintah",
                "value": 72.4,
                "value_raw": "72,4%",
                "unit": "%",
                "period": "Maret 2026",
                "geography": "Nasional",
                "definition": None,
                "source": {"page": 1, "excerpt": evidence_excerpt},
                "unknown_fields": ["definition"],
            }
        ],
    }


def make_normalization_json(**kwargs) -> str:
    return json.dumps(make_normalization_output(**kwargs))


def make_analysis_output(**overrides) -> dict:
    output = {
        "summary": "Survei melaporkan kepuasan kinerja pemerintah 72,4% dengan margin of error 2,9 poin.",
        "findings": [
            {
                "text": "Kepuasan kinerja pemerintah berada di 72,4%.",
                "evidence_ids": ["E1"],
                "rule_ids": [],
            }
        ],
        "caveats": [
            {
                "text": "Tanggal pelaksanaan lapangan tidak ditemukan di dokumen.",
                "evidence_ids": [],
                "rule_ids": ["R2"],
            }
        ],
        "visualizations": [
            {
                "id": "V1",
                "type": "metric_bar",
                "title": "Kepuasan kinerja pemerintah",
                "unit": "%",
                "data": [{"label": "Kepuasan", "value": 72.4, "evidence_id": "E1"}],
            }
        ],
    }
    output.update(overrides)
    return output


def make_analysis_json(**overrides) -> str:
    return json.dumps(make_analysis_output(**overrides))


def make_pdf_bytes(pages: int = 1, text: str = "Laporan survei contoh.") -> bytes:
    import textwrap

    doc = pymupdf.open()
    lines: list[str] = []
    for paragraph in text.split("\n"):
        lines.extend(textwrap.wrap(paragraph, width=90) or [""])
    for _ in range(pages):
        page = doc.new_page()
        y = 72
        for line in lines:
            page.insert_text((72, y), line)
            y += 14
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture(autouse=True)
def force_fake_llm(settings):
    settings.LLM_PROVIDER = "fake"


@pytest.fixture
def pdf_factory():
    return make_pdf_bytes


@pytest.fixture
def normalization_pages() -> dict[int, str]:
    return {1: PAGE_ONE_TEXT}


@pytest.fixture
def valid_metadata() -> dict:
    today = date.today()
    return {
        "title": "Survei Kepuasan Publik 2026",
        "publisher": "Lembaga Contoh",
        "publication_date": today,
        "period_start": date(today.year, 1, 1),
        "period_end": date(today.year, 6, 30),
        "source_url": "https://contoh.or.id/laporan",
        "notes": "",
    }


@pytest.fixture
def survey_factory(db):
    def _make(content: bytes | None = None, **overrides) -> Survey:
        if content is None:
            content = make_pdf_bytes()
        fields = {
            "title": "Survei Contoh",
            "publisher": "Lembaga Contoh",
            "publication_date": date(2026, 1, 10),
            "period_start": date(2026, 1, 1),
            "period_end": date(2026, 6, 30),
            "file_sha256": compute_sha256(content),
            "file": SimpleUploadedFile("laporan.pdf", content, content_type="application/pdf"),
            "page_count": 1,
            "status": Survey.Status.PENDING,
        }
        fields.update(overrides)
        return Survey.objects.create(**fields)

    return _make
