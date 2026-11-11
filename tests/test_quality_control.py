from app.agents.quality_control import run_quality_control


def test_qc_flags_missing_excerpt_and_bad_evidence_ref():
    claims = [{"id": "c1", "raw_excerpt": None, "page_number": 1, "document_id": "d1"}]
    evaluations = [{
        "id": "e1", "claim_id": "c1", "verdict": "valid", "confidence": 0.9,
        "explanation": "ok", "evidence_ids": ["missing-ev"], "metrics": {}, "limitations": []
    }]
    report = run_quality_control(claims, evaluations, [], {1}, set(), {})
    types = {i.type for i in report.issues}
    assert "claim_missing_excerpt" in types
    assert "eval_bad_evidence_ref" in types
    assert "c1" in report.needs_reevaluation


def test_qc_corrects_invalid_confidence_and_verdict():
    claims = [{"id": "c1", "raw_excerpt": "x", "page_number": 1, "document_id": "d1"}]
    evaluations = [{
        "id": "e1", "claim_id": "c1", "verdict": "bogus", "confidence": 5.0,
        "explanation": "ok", "evidence_ids": [], "metrics": {}, "limitations": None
    }]
    report = run_quality_control(claims, evaluations, [], {1}, set(), {})
    assert evaluations[0]["confidence"] is None
    assert evaluations[0]["verdict"] == "insufficient_evidence"
    assert evaluations[0]["limitations"] == []
    assert report.corrections
