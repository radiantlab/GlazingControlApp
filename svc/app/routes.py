from __future__ import annotations
from fastapi import APIRouter, HTTPException, Depends
from typing import List
from .models import Panel, Group, CommandRequest, CommandResult
from .service import ControlService
from .config import MODE

router = APIRouter()
svc: ControlService | None = None


def get_service() -> ControlService:
    global svc
    if svc is None:
        svc = ControlService()
    return svc


@router.get("/health")
def health():
    return {"status": "ok", "mode": MODE}


@router.get("/panels", response_model=List[Panel])
def list_panels(service: ControlService = Depends(get_service)) -> List[Panel]:
    return service.list_panels()


@router.get("/groups", response_model=List[Group])
def list_groups(service: ControlService = Depends(get_service)) -> List[Group]:
    return service.list_groups()


@router.post("/commands/set-level", response_model=CommandResult)
def set_level(
    body: CommandRequest, service: ControlService = Depends(get_service)
) -> CommandResult:
    if body.target_type == "panel":
        ok, applied, msg = service.set_panel_level(body.target_id, body.level)
    else:
        ok, applied, msg = service.set_group_level(body.target_id, body.level)

    if not ok:
        if msg in ("panel not found", "group not found"):
            raise HTTPException(status_code=404, detail=msg)
        if "dwell" in msg:
            raise HTTPException(status_code=429, detail=msg)
        raise HTTPException(status_code=500, detail=msg)

    return CommandResult(ok=True, applied_to=applied, message=msg)
