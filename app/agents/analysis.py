from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.config import settings


class ClaimEvaluation(BaseModel):
    claim_id: str
    verdict: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    explanation: str
    evidence_ids: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


def _normalize_number_token(tok: str) -> str:
    t = tok.strip()
    if "," in t and "." not in t:
        t = t.replace(",", ".")
    elif "," in t and "." in t and t.rfind(",") > t.rfind("."):
        t = t.replace(".", "").replace(",", ".")
    else:
        t = t.replace(",", "")
    return t


def _extract_numbers(text: str) -> set[str]:
    nums = set()
    for m in re.finditer(r"[+-]?\d+(?:[.,]\d+)?", text or ""):
        nums.add(_normalize_number_token(m.group(0)))
    return nums


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) > 2}


_STOP = {
    "the", "and", "for", "with", "that", "this", "from", "pada", "dan", "yang", "di", "ke",
    "dari", "sebesar", "tercatat", "menjadi", "indeks", "nilai", "triwulan", "komponen",
}


def _content_tokens(text: str) -> set[str]:
    return {t for t in _tokenize(text) if t not in _STOP}


def _value_close(claim_nums: set[str], ev_value: Any, raw_excerpt: str) -> bool:
    ev_nums = _extract_numbers(str(ev_value)) | _extract_numbers(raw_excerpt or "")
    if not ev_nums:
        return False
    for cn in claim_nums:
        try:
            c = float(cn)
        except Exception:
            continue
        for en in ev_nums:
            try:
                e = float(en)
            except Exception:
                continue
            if abs(c - e) <= max(0.01, abs(c) * 0.001):
                return True
    return False


def _score_evidence(claim_text: str, claim_nums: set[str], claim_terms: set[str], ev: dict) -> int:
    excerpt = ev.get("raw_excerpt") or ""
    metric_name = ev.get("metric") or ""
    period = ev.get("period") or ""
    ev_text = f"{excerpt} {metric_name} {period}"
    ev_terms = _content_tokens(ev_text)
    overlap = claim_terms & ev_terms
    num_match = _value_close(claim_nums, ev.get("value"), excerpt)
    period_match = bool(period) and period.lower() in claim_text.lower()
    return len(overlap) + (3 if num_match else 0) + (2 if period_match else 0)


def select_relevant_evidence(claim: dict, evidence: list[dict], limit: int | None = None) -> list[dict]:
    if not evidence:
        return []
    limit = int(limit or getattr(settings, "LLM_MAX_EVIDENCE_PER_CLAIM", 12) or 12)
    stmt = claim.get("statement") or ""
    raw = claim.get("raw_excerpt") or ""
    claim_text = f"{stmt} {raw}"
    claim_nums = _extract_numbers(claim_text)
    claim_terms = _content_tokens(claim_text)
    claim_page = claim.get("page_number")
    scored: list[tuple[int, dict]] = []
    for ev in evidence:
        score = _score_evidence(claim_text, claim_nums, claim_terms, ev)
        if claim_page is not None and ev.get("page_number") == claim_page:
            score += 1
        if score > 0:
            scored.append((score, ev))
    scored.sort(key=lambda x: x[0], reverse=True)
    selected = [ev for _, ev in scored[: max(1, limit)]]
    return selected if selected else evidence[: max(1, limit)]


def _heuristic_evaluate(claim: dict, evidence: list[dict]) -> ClaimEvaluation:
    stmt = claim.get("statement") or ""
    raw = claim.get("raw_excerpt") or ""
    claim_text = f"{stmt} {raw}"
    claim_nums = _extract_numbers(claim_text)
    claim_terms = _content_tokens(claim_text)
    matched: list[str] = []
    metrics: dict[str, Any] = {}
    for ev in evidence:
        score = _score_evidence(claim_text, claim_nums, claim_terms, ev)
        excerpt = ev.get("raw_excerpt") or ""
        num_match = _value_close(claim_nums, ev.get("value"), excerpt)
        overlap = claim_terms & _content_tokens(f"{excerpt} {ev.get('metric') or ''} {ev.get('period') or ''}")
        if score >= 3 or (num_match and len(overlap) >= 1):
            evid = str(ev.get("id"))
            if evid in matched:
                continue
            matched.append(evid)
            metrics[evid] = {
                "metric": ev.get("metric"),
                "value": ev.get("value"),
                "raw_value": ev.get("raw_value"),
                "unit": ev.get("unit"),
                "period": ev.get("period"),
                "population": ev.get("population"),
                "geography": ev.get("geography"),
                "page_number": ev.get("page_number"),
            }
    if matched:
        verdict = "valid"
        confidence = 0.7
        explanation = (
            "Claim is supported by matching numerical/contextual evidence extracted from the report; "
            "assessment is against the report's own evidence, not independent verification."
        )
        limitations = ["Automated matching used; manual review recommended."]
    else:
        verdict = "insufficient_evidence"
        confidence = 0.4
        explanation = "Insufficient matching evidence identified from extracted content to evaluate this claim."
        limitations = ["No matching evidence identified from extracted content."]
    return ClaimEvaluation(
        claim_id=str(claim.get("id")),
        verdict=verdict,
        confidence=confidence,
        explanation=explanation,
        evidence_ids=matched,
        metrics=metrics,
        limitations=limitations,
    )


def _slim_evidence_for_llm(evidence: list[dict]) -> list[dict]:
    max_excerpt = int(getattr(settings, "LLM_EVIDENCE_EXCERPT_MAX_CHARS", 220) or 220)
    slim = []
    for ev in evidence:
        excerpt = (ev.get("raw_excerpt") or "")
        if len(excerpt) > max_excerpt:
            excerpt = excerpt[: max_excerpt - 3] + "..."
        slim.append({
            "id": ev.get("id"),
            "metric": ev.get("metric"),
            "value": ev.get("value"),
            "raw_value": ev.get("raw_value"),
            "unit": ev.get("unit"),
            "period": ev.get("period"),
            "page_number": ev.get("page_number"),
            "raw_excerpt": excerpt,
        })
    return slim


def _llm_evaluate(claim: dict, evidence: list[dict]) -> ClaimEvaluation | None:
    try:
        from openai import OpenAI
    except Exception:
        return None
    if not getattr(settings, "QWEN_API_KEY", ""):
        return None
    if not getattr(settings, "LLM_EVALUATION", True):
        return None
    client = OpenAI(api_key=settings.QWEN_API_KEY, base_url=settings.QWEN_BASE_URL)
    compact_claim = {
        "id": claim.get("id"),
        "statement": claim.get("statement"),
        "raw_excerpt": claim.get("raw_excerpt"),
        "page_number": claim.get("page_number"),
    }
    slim_ev = _slim_evidence_for_llm(evidence)
    prompt = (
        "Evaluate the claim against provided evidence from the same report. "
        "Return ONLY JSON: {verdict, confidence, explanation, evidence_ids, metrics, limitations}. "
        "verdict one of: valid, questionable, invalid, insufficient_evidence. "
        "Match on numerical values (including comma/point decimals), units, periods, and context. "
        "Do not invent evidence. Missing evidence != false. "
        "State assessment is against report's own evidence, not independent verification.\n\n"
        f"CLAIM: {json.dumps(compact_claim, ensure_ascii=False)}\nEVIDENCE: {json.dumps(slim_ev, ensure_ascii=False)}"
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
        data["claim_id"] = str(claim.get("id"))
        data.setdefault("evidence_ids", [])
        data.setdefault("metrics", {})
        data.setdefault("limitations", [])
        return ClaimEvaluation(**data)
    except Exception:
        return None


def evaluate_claim(claim: dict, evidence: list[dict]) -> ClaimEvaluation:
    relevant = select_relevant_evidence(claim, evidence)
    heuristic = _heuristic_evaluate(claim, relevant)
    if heuristic.evidence_ids:
        return heuristic
    if not getattr(settings, "LLM_EVALUATION", True) or not getattr(settings, "QWEN_API_KEY", ""):
        return heuristic
    res = _llm_evaluate(claim, relevant)
    if res is not None:
        return res
    return heuristic

