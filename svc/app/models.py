from __future__ import annotations
from typing import List, Optional, Literal, Dict
from pydantic import BaseModel, Field, conint

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
    status: str = Field(description="Service status (always 'ok' if service is running)")
    mode: str = Field(description="Current operation mode: 'sim' (simulator) or 'real' (Halio API)")


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
