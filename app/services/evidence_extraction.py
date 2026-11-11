from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExtractedEvidence:
    metric: str
    value: float
    raw_value: str
    unit: str | None
    period: str | None
    geography: str | None
    raw_excerpt: str
    page_number: int


def _to_float(raw: str) -> float | None:
    s = raw.strip()
    # handle decimal separators: 52,75 and 52.75
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    elif s.count(",") == 1 and s.count(".") >= 1:
        # assume comma decimal if last separator is comma
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except Exception:
        return None


def _split_pages(full_text: str) -> list[tuple[int, str]]:
    parts = re.split(r"\[Page (\d+)\]\n?", full_text or "")
    pages: list[tuple[int, str]] = []
    if len(parts) >= 3:
        i = 1
        while i + 1 < len(parts):
            try:
                pn = int(parts[i])
            except Exception:
                i += 2
                continue
            pages.append((pn, parts[i + 1] or ""))
            i += 2
    if not pages and full_text:
        pages = [(1, full_text)]
    return pages


_NUM_RE = re.compile(r"(?<![A-Za-z])([+-]?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?)")


def _guess_unit(text: str, num_span: tuple[int, int]) -> str | None:
    tail = text[num_span[1] : num_span[1] + 12].lower()
    if tail.strip().startswith("%"):
        return "%"
    if "poin" in tail or "point" in tail:
        return "points"
    return None


def _guess_period(text: str) -> str | None:
    m = re.search(r"(Triwulan\s+[IVX]+-\d{4}|TW\s*[IVX]+\s*\d{4}|Q[1-4]\s*\d{4}|20\d{2})", text, re.IGNORECASE)
    return m.group(1) if m else None


def extract_evidence(full_text: str) -> list[ExtractedEvidence]:
    pages = _split_pages(full_text)
    evidence: list[ExtractedEvidence] = []
    seen: set[tuple[int, str, float, str | None]] = set()
    for pn, text in pages:
        for sent_m in re.finditer(r"[^.!?\n]*\d[^.!?\n]*[.!?]?", text):
            sent = re.sub(r"\s+", " ", sent_m.group(0)).strip()
            if len(sent) < 8:
                continue
            for m in _NUM_RE.finditer(sent):
                raw_v = m.group(1)
                val = _to_float(raw_v)
                if val is None:
                    continue
                unit = _guess_unit(sent, m.span(1))
                period = _guess_period(sent)
                # simple metric/entity hint: words around number
                left = sent[max(0, m.start(1) - 60) : m.start(1)].strip()
                metric = left.split()[-6:]
                metric_str = " ".join(metric) if metric else "value"
                key = (pn, raw_v, val, period)
                if key in seen:
                    continue
                seen.add(key)
                evidence.append(
                    ExtractedEvidence(
                        metric=metric_str[:255],
                        value=val,
                        raw_value=raw_v,
                        unit=unit,
                        period=period,
                        geography=None,
                        raw_excerpt=sent,
                        page_number=pn,
                    )
                )
    return evidence
