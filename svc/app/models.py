from __future__ import annotations
from typing import Annotated, List, Optional, Literal, Dict
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, StringConstraints, conint, model_validator

TintLevel = conint(ge=0, le=100)


class Panel(BaseModel):
    """Panel represents a single electrochromic panel."""
    id: str = Field(description="Panel identifier (e.g., P01, SK1)")
    name: str = Field(description="Human-readable panel name")
    level: TintLevel = Field(default=0, description="Current tint level (0-100)")
    last_change_ts: float = Field(default=0.0, description="Unix timestamp of last level change")


class Group(BaseModel):
    """Group represents a collection of panels that can be controlled together."""
    id: str = Field(description="Group identifier (e.g., G-facade, G-1)")
    name: str = Field(description="Human-readable group name")
    member_ids: List[str] = Field(default_factory=list, description="List of panel IDs in this group")


class CommandRequest(BaseModel):
    """Request to set tint level for a panel or group."""
    target_type: Literal["panel", "group"] = Field(description="Type of target to control")
    target_id: str = Field(description="Panel ID (e.g., P01) or Group ID (e.g., G-facade)")
    level: TintLevel = Field(description="Tint level to set (0-100)")
    actor: str = Field(default="api", description="Actor initiating the command")


class CommandResult(BaseModel):
    """Result of a tint level command."""
    ok: bool = Field(description="Whether the command was accepted")
    applied_to: List[str] = Field(description="List of panel IDs that were updated")
    message: str = Field(default="", description="Status message describing the result")


class Snapshot(BaseModel):
    panels: Dict[str, Panel] = Field(default_factory=dict)
    groups: Dict[str, Group] = Field(default_factory=dict)


class AuditEntry(BaseModel):
    """Audit log entry recording a control action."""
    ts: float = Field(description="Unix timestamp when the action occurred")
    actor: str = Field(description="Who/what initiated the action (e.g., 'api', 'user', 'schedule')")
    target_type: str = Field(description="Type of target: 'panel' or 'group'")
    target_id: str = Field(description="ID of the panel or group that was targeted")
    level: int = Field(description="Tint level that was requested (0-100)")
    applied_to: List[str] = Field(description="Panel IDs that were actually updated")
    result: str = Field(description="Result message (e.g., 'panel updated', 'dwell time not met')")

class HealthResponse(BaseModel):
    """Health check response."""
    status: Literal["ok", "degraded"] = Field(
        description="Overall service health"
    )
    environment: Literal["development", "production"] = Field(
        description="Current deployment environment"
    )
    control_source: Literal["simulated", "physical"] = Field(
        description="Effective panel-control source"
    )
    sensor_source: Literal["simulated", "physical", "mixed"] = Field(
        description="Effective sensor source"
    )
    sensor_acquisition: Literal["embedded", "external"] = Field(
        description="Whether this process or the Windows Sensor Agent owns acquisition"
    )
    sensor_status: Literal["healthy", "degraded"] = Field(
        description="Whether configured sensor clients are operating without errors"
    )
    sensor_errors: List[str] = Field(
        default_factory=list,
        description="Current sensor startup or polling errors",
    )


class GroupCreate(BaseModel):
    """Request to create a new group."""
    name: str = Field(description="Name for the new group")
    member_ids: List[str] = Field(default_factory=list, description="Panel IDs to include in the group")


class GroupUpdate(BaseModel):
    """Request to update an existing group."""
    name: Optional[str] = Field(default=None, description="New name for the group (optional)")
    member_ids: Optional[List[str]] = Field(default=None, description="New list of panel IDs (optional)")


class DeleteGroupResponse(BaseModel):
    """Response from deleting a group."""
    ok: bool = Field(description="Whether the deletion was successful")


class ErrorResponse(BaseModel):
    """Standard error response format."""
    detail: str = Field(description="Error message describing what went wrong")

class SensorInfo(BaseModel):
    id: str
    kind: str
    label: str
    location: Optional[str] = None
    config: Dict = Field(default_factory=dict)


class SensorReadingResponse(BaseModel):
    sensor_id: str
    metric: str
    value: float
    ts: float


class SensorLogEntry(BaseModel):
    sensor_id: str
    sensor_kind: Optional[str] = None
    sensor_label: Optional[str] = None
    metric: str
    value: float
    ts: float


class SensorSpectrumResponse(BaseModel):
    sensor_id: str
    ts: float
    wavelength_start: int
    wavelength_end: int
    wavelength_step: int
    values: List[float]


IngestIdentifier = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
]
MetricName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z][A-Za-z0-9_.:-]*$",
    ),
]


class SensorIngestEvent(BaseModel):
    """One physical observation forwarded by a host-side sensor collector."""

    model_config = ConfigDict(extra="forbid")

    event_id: IngestIdentifier
    sensor_id: IngestIdentifier
    observed_ts: FiniteFloat = Field(gt=0, description="Unix timestamp in seconds")
    metrics: Dict[MetricName, FiniteFloat] = Field(min_length=1, max_length=256)
    spectrum: Optional[List[FiniteFloat]] = Field(
        default=None,
        min_length=1,
        max_length=10000,
    )
    spectrum_wavelength_start: int = Field(default=380, ge=1)
    spectrum_wavelength_step: int = Field(default=1, ge=1)
    source: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)]] = None

    @model_validator(mode="after")
    def validate_spectrum_metadata(self) -> "SensorIngestEvent":
        if self.spectrum is None and (
            self.spectrum_wavelength_start != 380
            or self.spectrum_wavelength_step != 1
        ):
            raise ValueError(
                "spectrum wavelength metadata requires a spectrum"
            )
        return self


class SensorIngestBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: List[SensorIngestEvent] = Field(min_length=1, max_length=1000)


class SensorIngestResult(BaseModel):
    accepted: int
    duplicates: int


class RoutineRequest(BaseModel):
    name: str = Field(description="Name of the routine")
    code: str = Field(description="Python code to execute")
    mode: Literal["once", "interval"] = Field(description="Execution mode")
    interval_ms: Optional[int] = Field(default=None, description="Interval in milliseconds for interval mode")
    run_at_ts: Optional[float] = Field(default=None, description="Unix timestamp to run the routine at")
    indefinite: bool = Field(default=False, description="Whether an interval routine should run indefinitely")


class RoutineStatusResponse(BaseModel):
    id: str
    name: str
    code: str
    mode: str
    interval_ms: Optional[int]
    run_at_ts: Optional[float]
    indefinite: bool
    status: Literal["idle", "scheduled", "running", "error", "done", "stopped"]
    logs: List[str]
    duration_ms: Optional[int]


class SavedRoutine(BaseModel):
    name: str = Field(description="Name of the saved routine")
    code: str = Field(description="Python code")
