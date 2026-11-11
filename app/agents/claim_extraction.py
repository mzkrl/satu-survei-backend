from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field


class ExtractedClaim(BaseModel):
    statement: str
    category: str | None = None
    raw_excerpt: str
    page_number: int = Field(gt=0)


class ClaimExtractionResult(BaseModel):
    claims: list[ExtractedClaim] = Field(default_factory=list)
    no_evaluable_claims: bool = False


def _split_pages(full_text: str) -> list[tuple[int, str]]:
    parts = re.split(r"\[Page (\d+)\]\n?", full_text or "")
    pages: list[tuple[int, str]] = []
    # split gives ['', '1', 'text', '2', 'text', ...] or similar
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


def _heuristic_extract(full_text: str) -> ClaimExtractionResult:
    pages = _split_pages(full_text)
    claims: list[ExtractedClaim] = []
    seen: set[str] = set()
    patterns = [
        r"([^.!?\n]{10,}?\b\d+(?:[.,]\d+)?%[^.!?\n]{0,120}[.!?])",
        r"([^.!?\n]{10,}?\b(?:increased|decreased|rose|fell|grew|declined)\b[^.!?\n]{0,120}[.!?])",
        r"([^.!?\n]{10,}?\b(?:majority|percent|percentage|rate|average|total)\b[^.!?\n]{0,120}[.!?])",
    ]
    for pn, text in pages:
        for pat in patterns:
            for m in re.finditer(pat, text, flags=re.IGNORECASE):
                raw = re.sub(r"\s+", " ", m.group(1)).strip()
                stmt = raw
                key = stmt.lower()
                if key in seen or len(stmt) < 15:
                    continue
                seen.add(key)
                claims.append(
                    ExtractedClaim(
                        statement=stmt,
                        category="statistical_claim",
                        raw_excerpt=raw,
                        page_number=pn,
                    )
                )
    return ClaimExtractionResult(claims=claims, no_evaluable_claims=len(claims) == 0)


def _llm_extract(full_text: str) -> ClaimExtractionResult | None:
    try:
        from openai import OpenAI
        from app.config import settings
    except Exception:
        return None
    if not getattr(settings, "QWEN_API_KEY", ""):
        return None
    if not getattr(settings, "LLM_CLAIM_EXTRACTION", True):
        return None
    client = OpenAI(api_key=settings.QWEN_API_KEY, base_url=settings.QWEN_BASE_URL)
    max_chars = int(getattr(settings, "LLM_CLAIM_TEXT_MAX_CHARS", 8000) or 8000)
    text = (full_text or "")[:max_chars]
    prompt = (
        "Extract factual, evaluable claims from the document text below. "
        "Return ONLY JSON with key 'claims' as a list of objects: "
        "{statement, category, raw_excerpt, page_number}. "
        "Exclude opinions, recommendations, and table/figure references. "
        "If none, return {\"claims\": [], \"no_evaluable_claims\": true}.\n\nTEXT:\n"
        + text
    )
    try:
        resp = client.chat.completions.create(
            model=settings.QWEN_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        content = resp.choices[0].message.content or "{}"
        m = re.search(r"\{.*\}", content, re.DOTALL)
        data = json.loads(m.group(0) if m else content)
        claims = [ExtractedClaim(**c) for c in data.get("claims", [])]
        return ClaimExtractionResult(
            claims=claims,
            no_evaluable_claims=bool(data.get("no_evaluable_claims")) or len(claims) == 0,
        )
    except Exception:
        return None


def extract_claims(full_text: str) -> ClaimExtractionResult:
    result = _llm_extract(full_text)
    if result is not None:
        return result
    return _heuristic_extract(full_text)
