"""Typed public contracts used by the deterministic tools."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MissingPolicy(str, Enum):
    FAIL = "fail"
    IGNORE = "ignore"
    ERROR = "error"


class Bound(BaseModel):
    value: float
    inclusive: bool = True


class Condition(BaseModel):
    """One leaf in the prescription rule AST."""

    field: str
    variable: str
    unit: str | None = None
    lower: Bound | None = None
    upper: Bound | None = None
    season: Literal["spring", "summer", "autumn", "winter"] | None = None
    source_text: str
    operational_status: Literal["mapped", "provisional", "unmapped"] = "mapped"

    @model_validator(mode="after")
    def validate_bounds(self) -> Condition:
        if self.lower is None and self.upper is None:
            raise ValueError("condition needs at least one bound")
        if self.lower and self.upper and self.lower.value > self.upper.value:
            raise ValueError("lower bound exceeds upper bound")
        return self


class Prescription(BaseModel):
    """An AND rule over conditions, plus explicit unresolved source fields."""

    burn_class: str
    conditions: list[Condition]
    unresolved: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: str = "FMS-Prescriptions_2.xlsx"
    schema_version: str = "1.0"


class BurnWindow(BaseModel):
    location: str
    start: datetime
    end: datetime
    duration_hours: int = Field(ge=1)
    robustness: float | None = Field(default=None, ge=0.0, le=1.0)
    constraints: list[str] = Field(default_factory=list)


class ScheduleCandidate(BaseModel):
    id: str
    region: str
    start: datetime
    end: datetime
    area_hectares: float = Field(gt=0)
    robustness: float = Field(default=1.0, ge=0.0, le=1.0)
    quality: float = Field(default=0.0, ge=0.0)
    crew_demand: int = Field(default=1, ge=1)
    mobilisation_cost: float = Field(default=0.0, ge=0.0)

    @model_validator(mode="after")
    def validate_interval(self) -> ScheduleCandidate:
        if self.end <= self.start:
            raise ValueError("end must be after start")
        return self

    @property
    def duration_hours(self) -> float:
        return (self.end - self.start).total_seconds() / 3600.0

    @property
    def objective_value(self) -> float:
        return self.area_hectares * self.robustness + self.quality - self.mobilisation_cost


class ScheduleResult(BaseModel):
    method: Literal[
        "milp",
        "exact-fallback",
        "robust-milp",
        "robust-exact-fallback",
        "earliest-feasible",
        "highest-score",
    ]
    selected_ids: list[str]
    objective_value: float
    feasible: bool
    rejected: dict[str, str] = Field(default_factory=dict)
    solver_status: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolEnvelope(BaseModel):
    """Stable outer response shape suitable for function calling."""

    status: Literal["ok", "partial", "error", "needs_clarification"]
    data_version: str
    source: str
    constraints: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    result: Any = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class FindBurnWindowsRequest(BaseModel):
    times: list[datetime]
    data: dict[str, list[float | None]]
    prescription: Prescription
    min_duration_hours: int = Field(default=2, ge=1)
    location: str = "region"
    source_timezone: str = "UTC"
    missing_policy: MissingPolicy = MissingPolicy.ERROR
    data_version: str = "unknown"


class ExplainLimitingFactorsRequest(BaseModel):
    times: list[datetime]
    data: dict[str, list[float | None]]
    prescription: Prescription
    missing_policy: MissingPolicy = MissingPolicy.ERROR
    data_version: str = "unknown"


class ThresholdScenarioRequest(BaseModel):
    times: list[datetime]
    data: dict[str, list[float | None]]
    prescription: Prescription
    scenarios: dict[str, dict[str, float]]
    missing_policy: MissingPolicy = MissingPolicy.ERROR
    data_version: str = "unknown"


class RegionTrendRequest(BaseModel):
    years: list[int]
    suitable_rates: list[float]
    region: str
    block_size: int = Field(default=3, ge=1)
    bootstrap_samples: int = Field(default=500, ge=20)
    data_version: str = "unknown"

    @model_validator(mode="after")
    def validate_series(self) -> RegionTrendRequest:
        if len(self.years) != len(self.suitable_rates):
            raise ValueError("years and suitable_rates lengths differ")
        if any(rate < 0 or rate > 1 for rate in self.suitable_rates):
            raise ValueError("suitable_rates must be between 0 and 1")
        return self


class OptimizeScheduleRequest(BaseModel):
    candidates: list[ScheduleCandidate]
    crew_capacity: int = Field(ge=1)
    min_duration_hours: float = Field(default=2.0, gt=0)
    daily_capacity: int | None = Field(default=None, ge=1)
    data_version: str = "unknown"
