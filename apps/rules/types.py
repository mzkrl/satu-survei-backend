from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

RuleStatus = Literal["pass", "warn", "fail", "na"]


@dataclass(frozen=True)
class RuleOutcome:
    rule_id: str
    status: RuleStatus
    title: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
