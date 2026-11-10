from app.services.visualization import build_visualization


def test_visualization_summary_and_distribution():
    claims = [{"id": "c1", "statement": "s", "raw_excerpt": "r", "page_number": 1}]
    evals_by_claim = {"c1": {"verdict": "valid", "confidence": 0.8, "explanation": "e", "evidence_ids": [], "metrics": {}, "limitations": []}}
    qc = {"status": "passed", "issues": [], "corrections": []}
    out = build_visualization("a1", {"title": "T"}, claims, evals_by_claim, {}, qc)
    assert out["summary"]["total_claims"] == 1
    assert out["summary"]["valid"] == 1
    assert out["summary"]["questionable"] == 0
    assert isinstance(out["visualizations"]["verdict_distribution"], list)
    assert out["quality_control"]["status"] == "passed"
