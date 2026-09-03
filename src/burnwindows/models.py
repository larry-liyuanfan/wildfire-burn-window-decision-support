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
        "cvar-milp",
        "cvar-exact-fallback",
        "earliest-feasible",
        "highest-score",
    ]
    selected_ids: list[str]
    objective_value: float
    feasible: bool
    rejected: dict[str, str] = Field(default_factory=dict)
    solver_status: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolError(BaseModel):
    """Machine-readable failure returned after a request passed schema validation."""

    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class ToolProvenance(BaseModel):
    """Execution provenance without claiming that caller-supplied data was audited."""

    status: Literal["caller_asserted", "incomplete", "artifact_verified"]
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_sha: str
    source_references: list[str] = Field(default_factory=list)


class ToolExecution(BaseModel):
    """Service controls attached uniformly to stateless domain tools."""

    mode: Literal["direct", "service"] = "direct"
    timeout_seconds: float | None = Field(default=None, gt=0)
    elapsed_ms: float | None = Field(default=None, ge=0)
    idempotency_key: str | None = None
    replayed: bool = False
    checkpoint_mode: Literal["not_applicable_stateless", "artifact_checkpoint"] = (
        "not_applicable_stateless"
    )


class ToolEnvelope(BaseModel):
    """Stable outer response shape suitable for function calling."""

    schema_version: Literal["1.1"] = "1.1"
    tool_name: str | None = None
    status: Literal["ok", "partial", "error", "needs_clarification"]
    data_version: str
    source: str
    constraints: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    result: Any = None
    trace_id: str | None = None
    error: ToolError | None = None
    provenance: ToolProvenance | None = None
    execution: ToolExecution | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @model_validator(mode="after")
    def validate_error_contract(self) -> ToolEnvelope:
        if self.status == "error" and self.error is None:
            raise ValueError("error status requires error details")
        if self.status != "error" and self.error is not None:
            raise ValueError("non-error status cannot include error details")
        return self


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


class BurnUnitClimatologyRequest(BaseModel):
    """Read-only query over an allowlisted precomputed compact artifact."""

    artifact_id: str = Field(min_length=1, max_length=200)
    burn_ids: list[str] = Field(default_factory=list, max_length=176)
    year_start: int | None = Field(default=None, ge=1973, le=2023)
    year_end: int | None = Field(default=None, ge=1973, le=2023)

    @model_validator(mode="after")
    def validate_year_range(self) -> BurnUnitClimatologyRequest:
        if (
            self.year_start is not None
            and self.year_end is not None
            and self.year_end < self.year_start
        ):
            raise ValueError("year_end must not precede year_start")
        if len(self.burn_ids) != len(set(self.burn_ids)):
            raise ValueError("burn_ids must be unique")
        return self


class OptimizeScheduleRequest(BaseModel):
    candidates: list[ScheduleCandidate]
    crew_capacity: int = Field(ge=1)
    min_duration_hours: float = Field(default=2.0, gt=0)
    daily_capacity: int | None = Field(default=None, ge=1)
    data_version: str = "unknown"


class BurnUnit(BaseModel):
    """One official Joint Fuel Management Program planned-burn polygon."""

    burn_id: str
    name: str
    jfmp_year: str | None = None
    treatment_type: str | None = None
    district: str
    region: str | None = None
    objective: str | None = None
    planned_hectares: float = Field(gt=0)
    event_id: int | None = None


class BurnOutcome(BaseModel):
    """One official Fire History record for an executed burn."""

    burn_id: str
    name: str
    season: int | None = None
    start: datetime | None = None
    treatment_type: str | None = None
    treated_hectares: float = Field(gt=0)
    district: str
    region: str | None = None
    lead_agency: str | None = None


class DeriveFuelInputsRequest(BaseModel):
    """Inputs for literature-derived FMC and fuel-level-wind scenarios."""

    temperature_c: list[float]
    relative_humidity_pct: list[float]
    wind_10m_kmh: list[float]
    precipitation_mm: list[float] | None = None
    wind_reduction_factor: float = Field(default=0.33, gt=0.0, le=1.0)
    rain_guard_mm: float = Field(default=0.2, ge=0.0)
    data_version: str = "unknown"

    @model_validator(mode="after")
    def validate_lengths_and_ranges(self) -> DeriveFuelInputsRequest:
        lengths = {
            len(self.temperature_c),
            len(self.relative_humidity_pct),
            len(self.wind_10m_kmh),
        }
        if self.precipitation_mm is not None:
            lengths.add(len(self.precipitation_mm))
        if len(lengths) != 1:
            raise ValueError("fuel-input arrays have different lengths")
        if any(value <= 0 for value in self.temperature_c):
            raise ValueError("Viney FMC proxy requires temperature_c > 0")
        if any(value < 1 or value > 100 for value in self.relative_humidity_pct):
            raise ValueError("relative_humidity_pct must be in [1, 100]")
        if any(value < 0 for value in self.wind_10m_kmh):
            raise ValueError("wind_10m_kmh cannot be negative")
        if self.precipitation_mm is not None and any(value < 0 for value in self.precipitation_mm):
            raise ValueError("precipitation_mm cannot be negative")
        return self
