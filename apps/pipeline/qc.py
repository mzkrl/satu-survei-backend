from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from apps.agents.schemas import (
    NUMERIC_PROFILE_KEYS,
    PROFILE_KEYS,
    AnalysisOutput,
    NormalizationOutput,
)
from apps.pipeline.grounding import (
    GroundingTarget,
    check_grounding,
    normalize_number,
)

PARSE_ERROR_PREFIX = "JSON tidak valid"


@dataclass
class QCResult:
    ok: bool
    errors: list[str]
    parsed: Any = None
    grounding: dict[str, bool] = field(default_factory=dict)


def strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[A-Za-z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def parse_json(text: str) -> tuple[Any | None, str | None]:
    cleaned = strip_code_fence(text)
    try:
        return json.loads(cleaned), None
    except json.JSONDecodeError as exc:
        return None, f"{PARSE_ERROR_PREFIX}: {exc.msg} (posisi {exc.pos})"


def format_validation_errors(exc: ValidationError) -> list[str]:
    messages: list[str] = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"]) or "(akar)"
        messages.append(f"{location}: {error['msg']}")
    return messages


def build_grounding_targets(parsed: NormalizationOutput) -> list[GroundingTarget]:
    targets: list[GroundingTarget] = []
    for key in PROFILE_KEYS:
        profile_field = getattr(parsed.survey_profile, key)
        if profile_field.status != "found" or profile_field.source is None:
            continue
        numeric_value: float | None = None
        if key in NUMERIC_PROFILE_KEYS and profile_field.value is not None:
            numeric_value = float(profile_field.value)
        targets.append(
            GroundingTarget(
                key=key,
                page=profile_field.source.page,
                excerpt=profile_field.source.excerpt,
                numeric_value=numeric_value,
            )
        )
    for record in parsed.evidence_records:
        numeric_value = record.value
        if numeric_value is None:
            numeric_value = normalize_number(record.value_raw)
        targets.append(
            GroundingTarget(
                key=record.id,
                page=record.source.page,
                excerpt=record.source.excerpt,
                numeric_value=numeric_value,
            )
        )
    return targets


def run_normalization_qc(
    raw_text: str,
    *,
    pages: dict[int, str],
    grounding_min_ratio: float,
) -> QCResult:
    data, parse_error = parse_json(raw_text)
    if parse_error is not None:
        return QCResult(ok=False, errors=[parse_error], parsed=None)

    try:
        parsed = NormalizationOutput.model_validate(data)
    except ValidationError as exc:
        return QCResult(ok=False, errors=format_validation_errors(exc), parsed=None)

    targets = build_grounding_targets(parsed)
    grounding = check_grounding(targets, pages)
    ungrounded = [key for key, ok in grounding.items() if not ok]
    ratio = (len(grounding) - len(ungrounded)) / len(grounding) if grounding else 1.0

    errors: list[str] = []
    if ratio < grounding_min_ratio:
        errors.append(
            "kutipan tidak terverifikasi melebihi ambang "
            f"({ratio:.0%} < {grounding_min_ratio:.0%}): {', '.join(ungrounded)}"
        )

    return QCResult(ok=not errors, errors=errors, parsed=parsed, grounding=grounding)


CAVEAT_REQUIRED_STATUSES: frozenset[str] = frozenset({"warn", "fail", "na"})


def _collect_analysis_refs(parsed: Any) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    evidence_refs: list[tuple[str, str]] = []
    rule_refs: list[tuple[str, str]] = []
    blocks = list(parsed.findings) + list(parsed.caveats)
    for index, block in enumerate(blocks):
        location = f"findings/caveats[{index}]"
        for evidence_id in block.evidence_ids:
            evidence_refs.append((location, evidence_id))
        for rule_id in block.rule_ids:
            rule_refs.append((location, rule_id))
    for viz in parsed.visualizations:
        for point in viz.data:
            evidence_refs.append((f"visualizations.{viz.id}", point.evidence_id))
        for evidence_id in viz.evidence_ids:
            evidence_refs.append((f"visualizations.{viz.id}", evidence_id))
    return evidence_refs, rule_refs


def run_analysis_qc(
    raw_text: str,
    *,
    valid_evidence_ids: set[str],
    evidence_values: dict[str, float | None],
    valid_rule_ids: set[str],
    rule_statuses: set[str],
) -> QCResult:
    data, parse_error = parse_json(raw_text)
    if parse_error is not None:
        return QCResult(ok=False, errors=[parse_error], parsed=None)

    try:
        parsed = AnalysisOutput.model_validate(data)
    except ValidationError as exc:
        return QCResult(ok=False, errors=format_validation_errors(exc), parsed=None)

    errors: list[str] = []

    evidence_refs, rule_refs = _collect_analysis_refs(parsed)
    for location, evidence_id in evidence_refs:
        if evidence_id not in valid_evidence_ids:
            errors.append(f"{location}: evidence_id {evidence_id} tidak ada di bukti survei")
    for location, rule_id in rule_refs:
        if rule_id not in valid_rule_ids:
            errors.append(f"{location}: rule_id {rule_id} tidak ada di hasil Rule Engine")

    for viz in parsed.visualizations:
        if viz.type != "metric_bar":
            continue
        for point in viz.data:
            if point.evidence_id not in valid_evidence_ids:
                continue
            expected = evidence_values.get(point.evidence_id)
            if expected is None:
                errors.append(
                    f"visualizations.{viz.id}: bukti {point.evidence_id} tidak bernilai numerik"
                )
            elif abs(point.value - expected) > 1e-9:
                errors.append(
                    f"visualizations.{viz.id}: nilai {point.value} tidak sama dengan "
                    f"bukti {point.evidence_id} ({expected})"
                )

    if (rule_statuses & CAVEAT_REQUIRED_STATUSES) and not parsed.caveats:
        errors.append("caveats wajib diisi minimal 1 karena ada rule berstatus warn/fail/na")

    return QCResult(ok=not errors, errors=errors, parsed=parsed)
