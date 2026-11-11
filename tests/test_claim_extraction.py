from app.agents.claim_extraction import ClaimExtractionResult, ExtractedClaim, extract_claims


def test_extract_claims_heuristic_finds_statements():
    text = "[Page 1]\nThe unemployment rate decreased from 5.32% to 4.76% in 2023. This is good."
    res = extract_claims(text)
    assert isinstance(res, ClaimExtractionResult)
    assert isinstance(res.claims, list)


def test_extract_claims_no_evaluable():
    res = extract_claims("[Page 1]\nThis report contains figures and tables.")
    assert isinstance(res, ClaimExtractionResult)
    assert isinstance(res.no_evaluable_claims, bool)


def test_claim_model_has_provenance_fields():
    c = ExtractedClaim(statement="Unemployment fell by 2%.", category="statistical_claim", raw_excerpt="Unemployment fell by 2%.", page_number=3)
    assert c.page_number == 3
    assert c.raw_excerpt
