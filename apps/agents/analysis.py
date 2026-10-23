from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from apps.agents.llm import LLMClient
from apps.agents.schemas import AnalysisOutput
from apps.pipeline.qc import PARSE_ERROR_PREFIX, run_analysis_qc

PROMPT_VERSION = "analysis_v1"

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def load_analysis_prompt(version: str = PROMPT_VERSION) -> str:
    return (_PROMPTS_DIR / f"{version}.txt").read_text(encoding="utf-8")


def build_analysis_user_prompt(
    *,
    title: str,
    publisher: str,
    evidence_rows: list[dict[str, Any]],
    rule_rows: list[dict[str, Any]],
) -> str:
    payload = {
        "survey": {"title": title, "publisher": publisher},
        "evidence": evidence_rows,
        "rules": rule_rows,
    }
    return (
        "Data terverifikasi berikut adalah satu-satunya sumber fakta yang boleh kamu gunakan:\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        "Tulis narasi Kartu Survei dalam JSON sesuai skema."
    )


def build_analysis_retry_user(base_user: str, errors: list[str], raw_text: str | None = None) -> str:
    parts = [
        base_user,
        "",
        "Percobaan sebelumnya gagal QC dengan error berikut:",
        *[f"- {error}" for error in errors],
    ]
    if raw_text is not None:
        parts += ["", "Output sebelumnya (tidak valid, perbaiki):", raw_text]
    parts += ["", "Keluarkan JSON saja yang sudah diperbaiki."]
    return "\n".join(parts)


@dataclass
class AnalysisAttempt:
    attempt_no: int
    ok: bool
    error: str
    latency_ms: int
    model: str


@dataclass
class AnalysisOutcome:
    parsed: AnalysisOutput | None
    attempts: list[AnalysisAttempt]
    errors: list[str]
    raw_texts: list[str] = field(default_factory=list)


def analyze_with_retries(
    client: LLMClient,
    *,
    title: str,
    publisher: str,
    evidence_rows: list[dict[str, Any]],
    rule_rows: list[dict[str, Any]],
    valid_evidence_ids: set[str],
    evidence_values: dict[str, float | None],
    valid_rule_ids: set[str],
    rule_statuses: set[str],
    max_attempts: int = 3,
    timeout_s: int = 90,
    deadline: float | None = None,
) -> AnalysisOutcome:
    system = load_analysis_prompt()
    base_user = build_analysis_user_prompt(
        title=title,
        publisher=publisher,
        evidence_rows=evidence_rows,
        rule_rows=rule_rows,
    )
    user = base_user

    attempts: list[AnalysisAttempt] = []
    last_errors: list[str] = []

    for attempt_no in range(1, max_attempts + 1):
        if deadline is not None and time.monotonic() > deadline:
            raise TimeoutError("Batas waktu pipeline terlampaui.")
        response = client.complete(system=system, user=user, timeout_s=timeout_s)
        result = run_analysis_qc(
            response.text,
            valid_evidence_ids=valid_evidence_ids,
            evidence_values=evidence_values,
            valid_rule_ids=valid_rule_ids,
            rule_statuses=rule_statuses,
        )
        attempts.append(
            AnalysisAttempt(
                attempt_no=attempt_no,
                ok=result.ok,
                error="" if result.ok else "; ".join(result.errors),
                latency_ms=response.latency_ms,
                model=response.model,
            )
        )
        if result.ok:
            return AnalysisOutcome(parsed=result.parsed, attempts=attempts, errors=[])
        last_errors = result.errors
        include_raw = any(error.startswith(PARSE_ERROR_PREFIX) for error in result.errors)
        if attempt_no < max_attempts:
            user = build_analysis_retry_user(
                base_user,
                result.errors,
                response.text if include_raw else None,
            )

    return AnalysisOutcome(parsed=None, attempts=attempts, errors=last_errors)
