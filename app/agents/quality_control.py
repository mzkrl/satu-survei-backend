from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, Field


class QCIssue(BaseModel):
    type: str
    severity: str = "warning"
    message: str
    claim_id: str | None = None
    evaluation_id: str | None = None


class QCReport(BaseModel):
    status: str = "passed"  # passed | issues_found | failed
    issues: list[QCIssue] = Field(default_factory=list)
    corrections: list[str] = Field(default_factory=list)
    needs_reevaluation: list[str] = Field(default_factory=list)


def _is_valid_confidence(c: Any) -> bool:
    if c is None:
        return True
    try:
        f = float(c)
        return 0.0 <= f <= 1.0 and math.isfinite(f)
    except Exception:
        return False


def run_quality_control(
    claims: list[dict],
    evaluations: list[dict],
    evidence: list[dict],
    document_pages: set[int],
    valid_evidence_ids: set[str],
    evidence_by_id: dict[str, dict],
) -> QCReport:
    issues: list[QCIssue] = []
    corrections: list[str] = []
    needs_reeval: list[str] = []

    claims_by_id = {str(c.get("id")): c for c in claims}

    # Claim validation
    for c in claims:
        cid = str(c.get("id"))
        excerpt = c.get("raw_excerpt")
        pn = c.get("page_number")
        if not excerpt:
            issues.append(QCIssue(type="claim_missing_excerpt", message="Claim missing raw_excerpt", claim_id=cid))
        if pn is None:
            issues.append(QCIssue(type="claim_missing_page", message="Claim missing page_number", claim_id=cid))
        elif document_pages and pn not in document_pages:
            issues.append(QCIssue(type="claim_invalid_page", severity="error", message=f"Claim page {pn} not in document", claim_id=cid))

    # Evidence validation
    for ev in evidence:
        evid = str(ev.get("id"))
        try:
            float(ev.get("value"))
        except Exception:
            issues.append(QCIssue(type="evidence_invalid_value", severity="error", message="Evidence value not numeric", evaluation_id=evid))
        pn = ev.get("page_number")
        if pn is not None and document_pages and pn not in document_pages:
            issues.append(QCIssue(type="evidence_invalid_page", severity="error", message="Evidence page not in document", evaluation_id=evid))

    # Evaluation validation
    for evl in evaluations:
        cid = str(evl.get("claim_id"))
        evalid = str(evl.get("id", ""))
        claim = claims_by_id.get(cid)
        if not claim:
            issues.append(QCIssue(type="eval_orphan", severity="error", message="Evaluation references missing claim", claim_id=cid, evaluation_id=evalid))
            continue
        for eid in evl.get("evidence_ids") or []:
            se = str(eid)
            if se not in valid_evidence_ids:
                issues.append(QCIssue(type="eval_bad_evidence_ref", severity="error", message=f"Referenced evidence {se} does not exist", claim_id=cid, evaluation_id=evalid))
                if cid not in needs_reeval:
                    needs_reeval.append(cid)
                continue
            evdoc = evidence_by_id.get(se, {})
            if str(evdoc.get("document_id")) != str(claim.get("document_id")):
                issues.append(QCIssue(type="eval_evidence_context_mismatch", severity="error", message="Evidence not in same document context as claim", claim_id=cid, evaluation_id=evalid))
                if cid not in needs_reeval:
                    needs_reeval.append(cid)
        if not _is_valid_confidence(evl.get("confidence")):
            issues.append(QCIssue(type="eval_invalid_confidence", severity="error", message="Confidence out of [0,1]", claim_id=cid, evaluation_id=evalid))
            # deterministic correction
            evl["confidence"] = None
            corrections.append(f"Reset invalid confidence for claim {cid}")
        verdict = evl.get("verdict")
        if verdict not in {"valid", "questionable", "invalid", "insufficient_evidence"}:
            issues.append(QCIssue(type="eval_invalid_verdict", severity="error", message="Invalid verdict", claim_id=cid, evaluation_id=evalid))
            evl["verdict"] = "insufficient_evidence"
            corrections.append(f"Set verdict to insufficient_evidence for claim {cid}")
        if not evl.get("explanation"):
            issues.append(QCIssue(type="eval_missing_explanation", message="Missing explanation", claim_id=cid, evaluation_id=evalid))
        # consistency: insufficient_evidence but strong positive evidence refs
        if verdict == "insufficient_evidence" and (evl.get("evidence_ids") or []):
            issues.append(QCIssue(type="eval_inconsistent", message="insufficient_evidence verdict with evidence references", claim_id=cid, evaluation_id=evalid))
        # limitations present
        if evl.get("limitations") is None:
            evl["limitations"] = []
            corrections.append(f"Initialized limitations for claim {cid}")

    # Semantic completeness checks
    has_extractable_content = bool(document_pages)
    if has_extractable_content and len(evidence) == 0:
        issues.append(QCIssue(
            type="no_evidence_extracted",
            severity="error",
            message="Document contains extractable content but zero evidence records were produced.",
        ))
    if claims and all(len(evl.get("evidence_ids") or []) == 0 for evl in evaluations):
        issues.append(QCIssue(
            type="all_claims_unmatched",
            severity="error",
            message="All claims have zero associated evidence; matching or evidence extraction likely failed.",
        ))
        for evl in evaluations:
            cid = str(evl.get("claim_id"))
            if cid not in needs_reeval:
                needs_reeval.append(cid)
    # Provenance checks on evidence
    for ev in evidence:
        if ev.get("document_id") is None or ev.get("page_number") is None or not ev.get("raw_excerpt"):
            issues.append(QCIssue(
                type="evidence_missing_provenance",
                message="Evidence record missing provenance (document_id/page_number/raw_excerpt).",
                evaluation_id=str(ev.get("id")),
            ))

    status = "passed"
    if any(i.severity == "error" for i in issues):
        status = "issues_found"
    elif issues:
        status = "issues_found"

    return QCReport(status=status, issues=issues, corrections=corrections, needs_reevaluation=needs_reeval)
