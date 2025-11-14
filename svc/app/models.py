from __future__ import annotations
from typing import List, Optional, Literal, Dict
from pydantic import BaseModel, Field, conint

TintLevel = conint(ge=0, le=100)


class Panel(BaseModel):
    id: str
    name: str
    group_id: Optional[str] = None
    level: TintLevel = 0
    last_change_ts: float = 0.0


class Group(BaseModel):
    id: str
    name: str
    member_ids: List[str] = Field(default_factory=list)


class CommandRequest(BaseModel):
    target_type: Literal["panel", "group"]
    target_id: str
    level: TintLevel


class CommandResult(BaseModel):
    ok: bool
    applied_to: List[str]
    message: str = ""


class Snapshot(BaseModel):
    panels: Dict[str, Panel] = Field(default_factory=dict)
    groups: Dict[str, Group] = Field(default_factory=dict)


class AuditEntry(BaseModel):
    ts: float
    actor: str
    target_type: str
    target_id: str
    level: int
    applied_to: List[str]
    result: str

class GroupCreate(BaseModel):
    name: str
    member_ids: List[str]

class GroupCreate(BaseModel):
    name: str
    member_ids: List[str] = Field(default_factory=list)


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    member_ids: Optional[List[str]] = None

