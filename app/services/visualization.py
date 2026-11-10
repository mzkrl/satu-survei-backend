from __future__ import annotations

from collections import Counter
from typing import Any


def build_visualization(
    analysis_id: str,
    document: dict[str, Any],
    claims: list[dict[str, Any]],
    evaluations_by_claim: dict[str, dict[str, Any]],
    evidence_by_id: dict[str, dict[str, Any]],
    qc_report: dict[str, Any],
) -> dict[str, Any]:
    verdicts = []
    claim_items = []
    comparisons = []
    time_series = []

    for c in claims:
        cid = str(c.get("id"))
        evl = evaluations_by_claim.get(cid, {})
        v = evl.get("verdict", "insufficient_evidence")
        verdicts.append(v)
        ev_ids = [str(x) for x in (evl.get("evidence_ids") or [])]
        ev_items = [evidence_by_id[eid] for eid in ev_ids if eid in evidence_by_id]
        claim_items.append(
            {
                "claim_id": cid,
                "statement": c.get("statement"),
                "raw_excerpt": c.get("raw_excerpt"),
                "page_number": c.get("page_number"),
                "verdict": v,
                "confidence": evl.get("confidence"),
                "explanation": evl.get("explanation"),
                "evidence": ev_items,
                "metrics": evl.get("metrics") or {},
                "limitations": evl.get("limitations") or [],
            }
        )
        # derive simple comparisons from metrics
        metrics = evl.get("metrics") or {}
        if isinstance(metrics, dict):
            for k, m in metrics.items():
                if isinstance(m, dict) and m.get("value") is not None:
                    comparisons.append(
                        {
                            "claim_id": cid,
                            "evidence_id": k,
                            "metric": m.get("metric"),
                            "value": m.get("value"),
                            "unit": m.get("unit"),
                            "period": m.get("period"),
                        }
                    )
                    if m.get("period"):
                        time_series.append(
                            {
                                "claim_id": cid,
                                "period": m.get("period"),
                                "value": m.get("value"),
                                "metric": m.get("metric"),
                            }
                        )

    counts = Counter(verdicts)
    summary = {
        "total_claims": len(claims),
        "valid": counts.get("valid", 0),
        "questionable": counts.get("questionable", 0),
        "invalid": counts.get("invalid", 0),
        "insufficient_evidence": counts.get("insufficient_evidence", 0),
    }
    verdict_distribution = [
        {"verdict": k, "count": v} for k, v in summary.items() if k != "total_claims" and v > 0
    ]

    return {
        "analysis_id": analysis_id,
        "document": document,
        "summary": summary,
        "claims": claim_items,
        "visualizations": {
            "verdict_distribution": verdict_distribution,
            "statistical_comparisons": comparisons,
            "time_series": time_series,
        },
        "quality_control": qc_report,
    }
