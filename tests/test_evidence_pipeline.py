from app.services.evidence_extraction import extract_evidence, _to_float
from app.agents.analysis import evaluate_claim


def test_decimal_separator_normalization():
    assert _to_float("52,75") == 52.75
    assert _to_float("52.75") == 52.75
    assert _to_float("1.234,56") == 1234.56
    assert _to_float("0,08") == 0.08


def test_evidence_extraction_and_matching_numerical_claim():
    text = (
        "[Page 3]\n"
        "IKBM Triwulan III-2026 tercatat sebesar 52,75, berada di atas ambang netral 50.\n"
        "[Page 3]\n"
        "Nilai IKBM meningkat sebesar 0,08 poin dari 52,67 pada Triwulan II-2026 menjadi 52,75 pada Triwulan III-2026.\n"
    )
    evidence = extract_evidence(text)
    assert len(evidence) > 0
    ev_payloads = [
        {
            "id": f"e{i}",
            "metric": e.metric,
            "value": e.value,
            "raw_value": e.raw_value,
            "unit": e.unit,
            "period": e.period,
            "raw_excerpt": e.raw_excerpt,
            "page_number": e.page_number,
            "document_id": "d1",
        }
        for i, e in enumerate(evidence)
    ]
    claim = {
        "id": "c1",
        "statement": "IKBM Triwulan III-2026 tercatat sebesar 52,75.",
        "raw_excerpt": "IKBM Triwulan III-2026 tercatat sebesar 52,75, berada di atas ambang netral 50.",
        "page_number": 3,
        "document_id": "d1",
    }
    res = evaluate_claim(claim, ev_payloads)
    assert res.verdict in ("valid", "questionable")
    assert len(res.evidence_ids) >= 1


def test_evidence_matching_historical_comparison():
    text = (
        "[Page 3]\n"
        "Nilai IKBM meningkat sebesar 0,08 poin dari 52,67 pada Triwulan II-2026 menjadi 52,75 pada Triwulan III-2026.\n"
    )
    evidence = extract_evidence(text)
    ev_payloads = [
        {
            "id": f"e{i}", "metric": e.metric, "value": e.value, "raw_value": e.raw_value,
            "unit": e.unit, "period": e.period, "raw_excerpt": e.raw_excerpt,
            "page_number": e.page_number, "document_id": "d1",
        }
        for i, e in enumerate(evidence)
    ]
    claim = {
        "id": "c2",
        "statement": "IKBM increased by 0.08 points from Triwulan II-2026 to Triwulan III-2026.",
        "raw_excerpt": "Nilai IKBM meningkat sebesar 0,08 poin dari 52,67 pada Triwulan II-2026 menjadi 52,75 pada Triwulan III-2026.",
        "page_number": 3,
        "document_id": "d1",
    }
    res = evaluate_claim(claim, ev_payloads)
    assert len(res.evidence_ids) >= 1
    assert res.verdict != "insufficient_evidence"
