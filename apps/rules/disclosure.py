from __future__ import annotations

from dataclasses import dataclass

from apps.rules.types import RuleOutcome

RULE_ID = "R2"
TITLE = "Kelengkapan disclosure"

PASS_THRESHOLD = 8
WARN_THRESHOLD = 5
TOTAL_ITEMS = 9


@dataclass(frozen=True)
class ProfileInfo:
    found: bool
    page: int | None = None
    excerpt: str | None = None


_CHECKS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("sampling_method", "Metode sampling", ("sampling_method",)),
    ("sample_size", "Ukuran sampel", ("sample_size",)),
    ("fieldwork", "Tanggal pelaksanaan lapangan", ("fieldwork_start", "fieldwork_end")),
    ("sponsor_or_funder", "Pendana / pemberi mandat", ("sponsor_or_funder",)),
    ("population", "Definisi populasi", ("population",)),
    ("question_wording_disclosed", "Redaksi pertanyaan", ("question_wording_disclosed",)),
    ("mode", "Mode pengumpulan data", ("mode",)),
    (
        "moe_confidence",
        "Margin of error + tingkat kepercayaan",
        ("moe_claimed_pct", "confidence_level_pct"),
    ),
    ("weighting", "Pembobotan", ("weighting",)),
)


def evaluate_disclosure(profile: dict[str, ProfileInfo]) -> RuleOutcome:
    items: list[dict] = []
    found_count = 0
    missing_labels: list[str] = []

    for item_id, label, keys in _CHECKS:
        item_found = True
        page: int | None = None
        excerpt: str | None = None
        for key in keys:
            info = profile.get(key)
            if info is None or not info.found:
                item_found = False
            elif page is None:
                page = info.page
                excerpt = info.excerpt
        if item_found:
            found_count += 1
        else:
            missing_labels.append(label)
        items.append(
            {
                "item": item_id,
                "label": label,
                "found": item_found,
                "page": page,
                "excerpt": excerpt,
            }
        )

    if found_count >= PASS_THRESHOLD:
        status: str = "pass"
    elif found_count >= WARN_THRESHOLD:
        status = "warn"
    else:
        status = "fail"

    if not missing_labels:
        message = f"Semua {TOTAL_ITEMS} butir disclosure ditemukan di dokumen (skor {found_count}/{TOTAL_ITEMS})."
    else:
        message = (
            f"Skor disclosure {found_count}/{TOTAL_ITEMS}. "
            f"Tidak ditemukan di dokumen: {', '.join(missing_labels)}."
        )

    details = {
        "score": found_count,
        "total": TOTAL_ITEMS,
        "items": items,
    }
    return RuleOutcome(RULE_ID, status, TITLE, message, details)
