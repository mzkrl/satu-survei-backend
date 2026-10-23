from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

PROFILE_KEYS: tuple[str, ...] = (
    "sample_size",
    "sampling_method",
    "moe_claimed_pct",
    "confidence_level_pct",
    "fieldwork_start",
    "fieldwork_end",
    "sponsor_or_funder",
    "conducted_by",
    "population",
    "geography",
    "mode",
    "weighting",
    "question_wording_disclosed",
)

NUMERIC_PROFILE_KEYS: frozenset[str] = frozenset(
    {"sample_size", "moe_claimed_pct", "confidence_level_pct"}
)

CONTEXT_FIELD_NAMES: tuple[str, ...] = ("period", "unit", "geography", "definition")

ProfileValueT = TypeVar("ProfileValueT")


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(ge=1)
    excerpt: str = Field(min_length=1)


class ProfileField(BaseModel, Generic[ProfileValueT]):
    model_config = ConfigDict(extra="forbid")

    status: Literal["found", "unknown"]
    value: ProfileValueT | None = None
    source: Source | None = None

    @model_validator(mode="after")
    def _validate_status(self) -> "ProfileField[ProfileValueT]":
        if self.status == "found":
            if self.source is None:
                raise ValueError('status "found" memerlukan source (page + excerpt)')
            if self.value is None:
                raise ValueError('status "found" memerlukan value')
        else:
            if self.value is not None:
                raise ValueError('status "unknown" harus memiliki value null')
            if self.source is not None:
                raise ValueError('status "unknown" harus memiliki source null')
        return self


class SurveyProfileModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_size: ProfileField[float]
    sampling_method: ProfileField[str]
    moe_claimed_pct: ProfileField[float]
    confidence_level_pct: ProfileField[float]
    fieldwork_start: ProfileField[str]
    fieldwork_end: ProfileField[str]
    sponsor_or_funder: ProfileField[str]
    conducted_by: ProfileField[str]
    population: ProfileField[str]
    geography: ProfileField[str]
    mode: ProfileField[str]
    weighting: ProfileField[str]
    question_wording_disclosed: ProfileField[bool]


class EvidenceSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(ge=1)
    excerpt: str = Field(min_length=1)


class EvidenceRecordModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^E\d+$")
    label_original: str = Field(min_length=1)
    label_normalized: str = ""
    value: float | None = None
    value_raw: str = ""
    unit: str = ""
    period: str = ""
    geography: str = ""
    definition: str | None = None
    source: EvidenceSource
    unknown_fields: list[Literal["period", "unit", "geography", "definition"]] = Field(
        default_factory=list
    )


class NormalizationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    survey_profile: SurveyProfileModel
    evidence_records: list[EvidenceRecordModel] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def _check_unique_ids(self) -> "NormalizationOutput":
        ids = [record.id for record in self.evidence_records]
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        if duplicates:
            raise ValueError(f"id bukti duplikat: {', '.join(duplicates)}")
        return self


class ReferenceBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)


class MetricBarPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1)
    value: float
    evidence_id: str = Field(pattern=r"^E\d+$")


class Visualization(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^V\d+$")
    type: Literal["metric_bar", "metric_table"]
    title: str = Field(min_length=1)
    unit: str = ""
    data: list[MetricBarPoint] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_shape(self) -> "Visualization":
        if self.type == "metric_bar" and not self.data:
            raise ValueError("metric_bar memerlukan data (minimal satu titik)")
        if self.type == "metric_table" and not self.evidence_ids:
            raise ValueError("metric_table memerlukan evidence_ids")
        return self


class AnalysisOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)
    findings: list[ReferenceBlock] = Field(min_length=1, max_length=8)
    caveats: list[ReferenceBlock] = Field(default_factory=list)
    visualizations: list[Visualization] = Field(default_factory=list, max_length=4)
