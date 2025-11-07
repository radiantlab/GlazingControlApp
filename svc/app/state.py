from __future__ import annotations
import json
import os
import time
from typing import Dict, List
from .models import Panel, Group, Snapshot, AuditEntry
from .config import PANELS_FILE, AUDIT_FILE

def _ensure_dirs() -> None:
    os.makedirs(os.path.dirname(PANELS_FILE), exist_ok=True)
    os.makedirs(os.path.dirname(AUDIT_FILE), exist_ok=True)

def load_snapshot() -> Snapshot:
    _ensure_dirs()
    if not os.path.exists(PANELS_FILE):
        return Snapshot()
    with open(PANELS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    panels = {k: Panel(**v) for k, v in data.get("panels", {}).items()}
    groups = {k: Group(**v) for k, v in data.get("groups", {}).items()}
    return Snapshot(panels=panels, groups=groups)

def save_snapshot(s: Snapshot) -> None:
    _ensure_dirs()
    data = {
        "panels": {k: v.model_dump() for k, v in s.panels.items()},
        "groups": {k: v.model_dump() for k, v in s.groups.items()},
    }
    with open(PANELS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def append_audit(entry: AuditEntry) -> None:
    _ensure_dirs()
    row = entry.model_dump()
    # write one JSON per line for easy tailing
    with open(AUDIT_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")

def bootstrap_default_if_empty() -> Snapshot:
    snap = load_snapshot()
    if snap.panels:
        return snap
    # seed 18 facade panels and 2 skylights
    for i in range(1, 19):
        pid = f"P{i:02d}"
        snap.panels[pid] = Panel(id=pid, name=f"Facade {i}", group_id="G-facade")
    snap.panels["SK1"] = Panel(id="SK1", name="Skylight 1", group_id="G-skylights")
    snap.panels["SK2"] = Panel(id="SK2", name="Skylight 2", group_id="G-skylights")
    snap.groups["G-facade"] = Group(
        id="G-facade",
        name="Facade",
        member_ids=[f"P{i:02d}" for i in range(1, 19)],
    )
    snap.groups["G-skylights"] = Group(
        id="G-skylights",
        name="Skylights",
        member_ids=["SK1", "SK2"],
    )
    save_snapshot(snap)
    return snap

def audit(actor: str, target_type: str, target_id: str, level: int, applied: List[str], result: str) -> None:
    append_audit(AuditEntry(
        ts=time.time(),
        actor=actor,
        target_type=target_type,
        target_id=target_id,
        level=level,
        applied_to=applied,
        result=result,
    ))
