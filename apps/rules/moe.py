from __future__ import annotations

import math

from apps.rules.types import RuleOutcome

RULE_ID = "R1"
TITLE = "Margin of error"

Z_TABLE: dict[float, float] = {90.0: 1.645, 95.0: 1.96, 99.0: 2.576}
DEFAULT_CONFIDENCE_PCT = 95.0
TOLERANCE_POINTS = 0.3

NON_PROBABILITY_KEYWORDS: tuple[str, ...] = (
    "quota",
    "kuota",
    "online panel",
    "convenience",
    "snowball",
)

ASSUMPTION_BASE = "asumsi: sampel acak sederhana (SRS), p = 0.5"


def z_for_confidence(confidence_pct: float) -> float:
    if not 0.0 < confidence_pct < 100.0:
        confidence_pct = DEFAULT_CONFIDENCE_PCT
    if confidence_pct in Z_TABLE:
        return Z_TABLE[confidence_pct]
    from scipy.stats import norm

    return float(norm.ppf(1 - (1 - confidence_pct / 100) / 2))


def compute_expected_moe(n: float, z: float) -> float:
    return z * math.sqrt(0.25 / n) * 100


def is_non_probability(method: str) -> bool:
    lowered = method.lower()
    return any(keyword in lowered for keyword in NON_PROBABILITY_KEYWORDS)


def evaluate_moe(
    *,
    sample_size: float | None,
    moe_claimed_pct: float | None,
    confidence_level_pct: float | None,
    sampling_method: str | None,
) -> RuleOutcome:
    details: dict = {
        "n": sample_size,
        "z": None,
        "moe_expected": None,
        "moe_claimed": moe_claimed_pct,
        "selisih": None,
        "asumsi": ASSUMPTION_BASE,
    }

    if sample_size is None or moe_claimed_pct is None:
        missing: list[str] = []
        if sample_size is None:
            missing.append("ukuran sampel")
        if moe_claimed_pct is None:
            missing.append("klaim margin of error")
        message = (
            f"Tidak ditemukan di dokumen: {', '.join(missing)}. "
            f"Perbandingan MoE tidak dapat dihitung ({ASSUMPTION_BASE})."
        )
        return RuleOutcome(RULE_ID, "na", TITLE, message, details)

    confidence = confidence_level_pct
    if confidence is None:
        confidence = DEFAULT_CONFIDENCE_PCT
        details["asumsi"] = f"{ASSUMPTION_BASE}; tingkat kepercayaan tidak ditemukan, diasumsikan 95%"

    z = z_for_confidence(confidence)
    expected = compute_expected_moe(sample_size, z)
    selisih = moe_claimed_pct - expected
    details.update(
        {
            "z": z,
            "moe_expected": round(expected, 3),
            "selisih": round(selisih, 3),
        }
    )

    method = (sampling_method or "").strip()
    if method and is_non_probability(method):
        message = (
            f"Metode sampling terindikasi non-probabilitas ({method}). "
            "MoE klasik tidak sepenuhnya berlaku untuk desain tersebut; "
            f"klaim {moe_claimed_pct:g}% tidak dapat diverifikasi dengan formula SRS ({ASSUMPTION_BASE})."
        )
        return RuleOutcome(RULE_ID, "warn", TITLE, message, details)

    if selisih < -TOLERANCE_POINTS:
        message = (
            f"Klaim MoE {moe_claimed_pct:g}% lebih kecil dari hitungan acak sederhana "
            f"{expected:.2f}% (selisih {abs(selisih):.2f} poin; {ASSUMPTION_BASE}, z={z:g})."
        )
        return RuleOutcome(RULE_ID, "fail", TITLE, message, details)

    if selisih > TOLERANCE_POINTS:
        message = (
            f"Klaim MoE {moe_claimed_pct:g}% lebih besar dari hitungan acak sederhana "
            f"{expected:.2f}% (selisih {selisih:.2f} poin) — konsisten dengan design effect "
            f"pada multistage sampling ({ASSUMPTION_BASE}, z={z:g})."
        )
        return RuleOutcome(RULE_ID, "pass", TITLE, message, details)

    message = (
        f"Klaim MoE {moe_claimed_pct:g}% berada dalam toleransi {TOLERANCE_POINTS} poin dari "
        f"hitungan acak sederhana {expected:.2f}% ({ASSUMPTION_BASE}, z={z:g})."
    )
    return RuleOutcome(RULE_ID, "pass", TITLE, message, details)
