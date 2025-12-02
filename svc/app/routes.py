from __future__ import annotations
from fastapi import APIRouter, HTTPException, Depends, status, Query
from .models import (
    Panel, Group, CommandRequest, CommandResult, GroupCreate, GroupUpdate, 
    AuditEntry, HealthResponse, DeleteGroupResponse, ErrorResponse, SensorInfo,
    SensorReadingResponse
)
from typing import List
from .service import ControlService
from .config import MODE
from .state import (
    fetch_audit_entries,
    list_sensors as _list_sensors,
    fetch_latest_readings as _fetch_latest_readings,
    fetch_readings as _fetch_readings,
)


router = APIRouter()
svc: ControlService | None = None


def get_service() -> ControlService:
    global svc
    if svc is None:
        svc = ControlService()
    return svc


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns service health status and current operation mode (sim or real)",
    tags=["Health"]
)
def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="ok", mode=MODE)


@router.get(
    "/panels",
    response_model=List[Panel],
    summary="List all panels",
    description="Returns a list of all panels with their current tint levels and state",
    tags=["Panels"]
)
def list_panels(service: ControlService = Depends(get_service)) -> List[Panel]:
    """Get all panels."""
    return service.list_panels()


@router.get(
    "/groups",
    response_model=List[Group],
    summary="List all groups",
    description="Returns a list of all groups with their member panel IDs",
    tags=["Groups"]
)
def list_groups(service: ControlService = Depends(get_service)) -> List[Group]:
    """Get all groups."""
    return service.list_groups()


@router.post(
    "/commands/set-level",
    response_model=CommandResult,
    status_code=status.HTTP_200_OK,
    summary="Set tint level",
    description="Set the tint level (0-100) for a panel or group. Enforces dwell time between changes.",
    responses={
        200: {"description": "Command accepted"},
        404: {"model": ErrorResponse, "description": "Panel or group not found"},
        429: {"model": ErrorResponse, "description": "Dwell time not met - panel changed too recently"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    tags=["Commands"]
)
def set_level(
    body: CommandRequest, service: ControlService = Depends(get_service)
) -> CommandResult:
    """Set tint level for a panel or group."""
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


@router.post(
    "/groups",
    response_model=Group,
    status_code=status.HTTP_201_CREATED,
    summary="Create a group",
    description="Create a new group with specified name and member panel IDs. Only available in sim mode.",
    responses={
        201: {"description": "Group created successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request or operation not supported in current mode"}
    },
    tags=["Groups"]
)
def create_group(body: GroupCreate, service: ControlService = Depends(get_service)) -> Group:
    """Create a new group."""
    try:
        return service.create_group(body.name, body.member_ids)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))



@router.patch(
    "/groups/{group_id}",
    response_model=Group,
    summary="Update a group",
    description="Update a group's name and/or member panel IDs. Only available in sim mode.",
    responses={
        200: {"description": "Group updated successfully"},
        404: {"model": ErrorResponse, "description": "Group not found"},
        400: {"model": ErrorResponse, "description": "Invalid request or operation not supported in current mode"}
    },
    tags=["Groups"]
)
def update_group(
    group_id: str,
    body: GroupUpdate,
    service: ControlService = Depends(get_service),
) -> Group:
    """Update an existing group."""
    try:
        return service.update_group(group_id, body.name, body.member_ids)
    except KeyError:
        raise HTTPException(status_code=404, detail="group not found")
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete(
    "/groups/{group_id}",
    response_model=DeleteGroupResponse,
    summary="Delete a group",
    description="Delete a group by ID. Only available in sim mode.",
    responses={
        200: {"description": "Group deleted successfully"},
        404: {"model": ErrorResponse, "description": "Group not found"}
    },
    tags=["Groups"]
)
def delete_group(group_id: str, service: ControlService = Depends(get_service)) -> DeleteGroupResponse:
    """Delete a group."""
    ok = service.delete_group(group_id)
    if not ok:
        raise HTTPException(status_code=404, detail="group not found")
    return DeleteGroupResponse(ok=True)


@router.get(
    "/logs/audit",
    response_model=List[AuditEntry],
    summary="Get audit logs",
    description="Retrieve audit log entries with pagination support",
    tags=["Logs"]
)
def get_audit_logs(
    limit: int = Query(default=500, ge=1, le=1000, description="Maximum number of entries to return"),
    offset: int = Query(default=0, ge=0, description="Number of entries to skip")
) -> List[AuditEntry]:
    """Get audit log entries."""
    rows = fetch_audit_entries(limit=limit, offset=offset)
    return [AuditEntry(**row) for row in rows]


@router.get(
    "/sensors",
    response_model=List[SensorInfo],
    summary="List connected sensors",
    tags=["Sensors"],
)
def list_sensors() -> List[SensorInfo]:
    rows = _list_sensors()
    return [
        SensorInfo(
            id=r["id"],
            kind=r["kind"],
            label=r["label"],
            location=r.get("location"),
            config=r.get("config", {}),
        )
        for r in rows
    ]


@router.get(
    "/metrics/latest",
    response_model=List[SensorReadingResponse],
    summary="Latest metric values per sensor/metric",
    tags=["Sensors"],
)
def get_latest_metrics() -> List[SensorReadingResponse]:
    rows = _fetch_latest_readings()
    return [SensorReadingResponse(**r) for r in rows]


@router.get(
    "/metrics/history",
    response_model=List[SensorReadingResponse],
    summary="Historical readings for a sensor + metric",
    tags=["Sensors"],
)
def get_metric_history(
    sensor_id: str = Query(..., description="Sensor ID, e.g. KM1-00"),
    metric: str = Query(..., description="Metric name, e.g. 'lux'"),
    ts_from: float = Query(..., description="Start timestamp (unix seconds)"),
    ts_to: float = Query(..., description="End timestamp (unix seconds)"),
) -> List[SensorReadingResponse]:
    rows = _fetch_readings(sensor_id=sensor_id, metric=metric, ts_from=ts_from, ts_to=ts_to)
    return [SensorReadingResponse(**r) for r in rows]