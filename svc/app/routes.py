from __future__ import annotations
from fastapi import APIRouter, HTTPException, Depends, status, Query
from fastapi.responses import Response
from .models import (
    Panel, Group, CommandRequest, CommandResult, GroupCreate, GroupUpdate, 
    AuditEntry, HealthResponse, DeleteGroupResponse, ErrorResponse, SensorInfo,
    SensorReadingResponse, SensorLogEntry, RoutineRequest, RoutineStatusResponse, SavedRoutine
)
from typing import List, Optional
import csv
import io
from datetime import datetime, timezone
from .service import ControlService
from .config import MODE
from .state import (
    fetch_audit_entries,
    list_sensors as _list_sensors,
    fetch_latest_readings as _fetch_latest_readings,
    fetch_readings as _fetch_readings,
    fetch_sensor_log_entries as _fetch_sensor_log_entries,
    list_routines,
    get_routine,
    list_saved_routines,
    save_saved_routine,
    delete_saved_routine
)
from .routines.manager import start_routine, stop_routine, remove_routine, active_routines
import uuid


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
        ok, applied, msg = service.set_panel_level(body.target_id, body.level, body.actor)
    else:
        ok, applied, msg = service.set_group_level(body.target_id, body.level, body.actor)

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
        return service.create_group(body.name, body.member_ids, body.layout)
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
        return service.update_group(group_id, body.name, body.member_ids, body.layout)
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
    "/logs/audit/export",
    summary="Export audit logs as CSV",
    description="Export audit log entries as a CSV file with optional filtering",
    tags=["Logs"]
)
def export_audit_logs_csv(
    limit: int = Query(default=10000, ge=1, le=100000, description="Maximum number of entries to export"),
    start_date: Optional[float] = Query(None, description="Start timestamp (Unix seconds)"),
    end_date: Optional[float] = Query(None, description="End timestamp (Unix seconds)"),
    target_type: Optional[str] = Query(None, description="Filter by target type (panel/group)"),
    target_filter: Optional[str] = Query(None, description="Filter by target ID or applied_to"),
    result_filter: Optional[str] = Query(None, description="Filter by result text"),
    sort_field: Optional[str] = Query(None, description="Field to sort by"),
    sort_dir: Optional[str] = Query(None, description="Direction to sort by")
) -> Response:
    """Export audit log entries as CSV with optional filtering."""
    # If any filters are provided, fetch without limit first to ensure we get all entries
    # that might match the filters, then apply limit after filtering.
    # This prevents missing entries that fall outside the most recent N entries.
    has_filters = (
        start_date is not None or 
        end_date is not None or 
        (target_type and target_type != "all") or 
        target_filter or 
        result_filter or
        sort_field or
        sort_dir
    )

    #check for potential injection
    allowed_fields = ["ts", "actor", "target_type", "target_id", "level"]
    allowed_dirs = ["desc", "asc"]
    
    if (sort_field is None) or (sort_field not in allowed_fields):
        sort_field = "ts"
    if (sort_dir is None) or (sort_dir not in allowed_dirs):
        sort_dir = "desc"

    if has_filters:
        # Filters require fetching all entries to find matches across the full range
        # Use a very high limit to get all entries (practical maximum for exports)
        rows = fetch_audit_entries(limit=1000000, offset=0, input_sort_field=sort_field, input_sort_dir=sort_dir)
    else:
        # No filters, safe to apply limit upfront for performance
        rows = fetch_audit_entries(limit=limit, offset=0, input_sort_field=sort_field, input_sort_dir=sort_dir)
    
    # Apply filters (matching frontend filtering logic)
    filtered_rows = rows
    
    # Date range filtering
    if start_date is not None:
        filtered_rows = [r for r in filtered_rows if r["ts"] >= start_date]
    if end_date is not None:
        filtered_rows = [r for r in filtered_rows if r["ts"] <= end_date]
    
    # Target type filtering
    if target_type and target_type != "all":
        filtered_rows = [r for r in filtered_rows if r["target_type"] == target_type]
    
    # Target ID/applied_to filtering
    if target_filter:
        needle = target_filter.lower()
        filtered_rows = [
            r for r in filtered_rows
            if needle in r["target_id"].lower() or
            any(needle in id.lower() for id in r["applied_to"])
        ]
    
    # Result filtering
    if result_filter:
        needle = result_filter.lower()
        filtered_rows = [r for r in filtered_rows if needle in r["result"].lower()]
    
    # Apply limit to filtered results (only if filters were used, since limit was already applied otherwise)
    if has_filters:
        filtered_rows = filtered_rows[:limit]
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        "Timestamp",
        "Actor",
        "Target Type",
        "Target ID",
        "Level",
        "Applied To",
        "Result"
    ])
    
    # Write data rows
    for row in filtered_rows:
        # Convert timestamp to human-readable format using UTC timezone
        # This ensures consistency regardless of server timezone, matching the UTC-based Unix timestamps
        human_readable_ts = datetime.fromtimestamp(row["ts"], tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        writer.writerow([
            human_readable_ts,
            row["actor"],
            row["target_type"],
            row["target_id"],
            row["level"],
            ", ".join(row["applied_to"]),
            row["result"]
        ])
    
    # Generate filename with current date in UTC to match UTC timestamps in CSV
    filename = f"audit_logs_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_sorted_{sort_field}_{sort_dir}.csv"
    
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get(
    "/logs/sensors",
    response_model=List[SensorLogEntry],
    summary="Get sensor logs",
    description="Retrieve sensor reading log entries with optional filtering and sorting",
    tags=["Logs"],
)
def get_sensor_logs(
    limit: int = Query(default=500, ge=1, le=5000, description="Maximum number of entries to return"),
    offset: int = Query(default=0, ge=0, description="Number of entries to skip"),
    sensor_id: Optional[str] = Query(None, description="Filter by sensor ID"),
    metric: Optional[str] = Query(None, description="Filter by metric name"),
    ts_from: Optional[float] = Query(None, description="Start timestamp (Unix seconds)"),
    ts_to: Optional[float] = Query(None, description="End timestamp (Unix seconds)"),
    sort_field: Optional[str] = Query(None, description="Field to sort by"),
    sort_dir: Optional[str] = Query(None, description="Direction to sort by (asc/desc)"),
) -> List[SensorLogEntry]:
    allowed_fields = ["ts", "sensor_id", "metric", "value", "sensor_kind", "sensor_label"]
    allowed_dirs = ["desc", "asc"]

    if (sort_field is None) or (sort_field not in allowed_fields):
        sort_field = "ts"
    if (sort_dir is None) or (sort_dir not in allowed_dirs):
        sort_dir = "desc"

    rows = _fetch_sensor_log_entries(
        limit=limit,
        offset=offset,
        sensor_id=sensor_id,
        metric=metric,
        ts_from=ts_from,
        ts_to=ts_to,
        input_sort_field=sort_field,
        input_sort_dir=sort_dir,
    )
    return [SensorLogEntry(**r) for r in rows]


@router.get(
    "/logs/sensors/export",
    summary="Export sensor logs as CSV",
    description="Export sensor reading logs as a CSV file with optional filtering and sorting",
    tags=["Logs"],
)
def export_sensor_logs_csv(
    limit: int = Query(default=100000, ge=1, le=1000000, description="Maximum number of entries to export"),
    sensor_id: Optional[str] = Query(None, description="Filter by sensor ID"),
    metric: Optional[str] = Query(None, description="Filter by metric name"),
    ts_from: Optional[float] = Query(None, description="Start timestamp (Unix seconds)"),
    ts_to: Optional[float] = Query(None, description="End timestamp (Unix seconds)"),
    sort_field: Optional[str] = Query(None, description="Field to sort by"),
    sort_dir: Optional[str] = Query(None, description="Direction to sort by (asc/desc)"),
) -> Response:
    allowed_fields = ["ts", "sensor_id", "metric", "value", "sensor_kind", "sensor_label"]
    allowed_dirs = ["desc", "asc"]

    if (sort_field is None) or (sort_field not in allowed_fields):
        sort_field = "ts"
    if (sort_dir is None) or (sort_dir not in allowed_dirs):
        sort_dir = "desc"

    rows = _fetch_sensor_log_entries(
        limit=limit,
        offset=0,
        sensor_id=sensor_id,
        metric=metric,
        ts_from=ts_from,
        ts_to=ts_to,
        input_sort_field=sort_field,
        input_sort_dir=sort_dir,
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Timestamp",
            "Sensor ID",
            "Sensor Kind",
            "Sensor Label",
            "Metric",
            "Value",
        ]
    )

    for row in rows:
        human_readable_ts = datetime.fromtimestamp(row["ts"], tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
        writer.writerow(
            [
                human_readable_ts,
                row["sensor_id"],
                row.get("sensor_kind") or "",
                row.get("sensor_label") or "",
                row["metric"],
                row["value"],
            ]
        )

    filename = (
        f"sensor_logs_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        f"_sorted_{sort_field}_{sort_dir}.csv"
    )

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


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
    sensor_id: str = Query(..., description="Sensor ID, e.g. T10A1-H1"),
    metric: str = Query(..., description="Metric name, e.g. 'lux'"),
    ts_from: float = Query(..., description="Start timestamp (unix seconds)"),
    ts_to: float = Query(..., description="End timestamp (unix seconds)"),
) -> List[SensorReadingResponse]:
    rows = _fetch_readings(sensor_id=sensor_id, metric=metric, ts_from=ts_from, ts_to=ts_to)
    return [SensorReadingResponse(**r) for r in rows]


# --- ROUTINES -------------------------------------------------------------

@router.get(
    "/routines",
    response_model=List[RoutineStatusResponse],
    summary="List all routines",
    tags=["Routines"],
)
def get_routines() -> List[RoutineStatusResponse]:
    routines = list_routines()
    out = []
    for r in routines:
        rid = r["id"]
        logs = []
        if rid in active_routines:
            logs = active_routines[rid].get("logs", [])

        out.append(RoutineStatusResponse(
            id=rid,
            name=r["name"],
            code=r["code"],
            mode=r["mode"],
            interval_ms=r.get("interval_ms"),
            run_at_ts=r.get("run_at_ts"),
            indefinite=r["indefinite"],
            status=r["status"],
            logs=logs,
            duration_ms=None
        ))
    return out


@router.post(
    "/routines",
    response_model=RoutineStatusResponse,
    summary="Create and start a new routine",
    tags=["Routines"],
)
def create_routine(body: RoutineRequest) -> RoutineStatusResponse:
    rid = str(uuid.uuid4())
    start_routine(
        routine_id=rid,
        name=body.name,
        code=body.code,
        mode=body.mode,
        interval_ms=body.interval_ms,
        run_at_ts=body.run_at_ts,
        indefinite=body.indefinite
    )
    
    # fetch back to return
    r = get_routine(rid)
    logs = active_routines.get(rid, {}).get("logs", [])
    
    return RoutineStatusResponse(
        id=rid,
        name=r["name"],
        code=r["code"],
        mode=r["mode"],
        interval_ms=r.get("interval_ms"),
        run_at_ts=r.get("run_at_ts"),
        indefinite=r["indefinite"],
        status=r["status"],
        logs=logs,
        duration_ms=None
    )


@router.delete(
    "/routines/{routine_id}",
    summary="Stop and delete a routine",
    tags=["Routines"],
)
def delete_routine_endpoint(routine_id: str):
    r = get_routine(routine_id)
    if not r:
        raise HTTPException(status_code=404, detail="Routine not found")
        
    remove_routine(routine_id)
    return {"ok": True}


@router.post(
    "/routines/{routine_id}/stop",
    summary="Stop a running routine",
    tags=["Routines"],
)
def stop_routine_endpoint(routine_id: str):
    r = get_routine(routine_id)
    if not r:
        raise HTTPException(status_code=404, detail="Routine not found")
        
    stop_routine(routine_id)
    return {"ok": True}


@router.get(
    "/saved-routines",
    response_model=List[SavedRoutine],
    summary="List all saved routines",
    tags=["Routines"],
)
def get_saved_routines() -> List[SavedRoutine]:
    return [SavedRoutine(**r) for r in list_saved_routines()]


@router.post(
    "/saved-routines",
    response_model=SavedRoutine,
    summary="Save a routine to the server",
    tags=["Routines"],
)
def create_saved_routine(body: SavedRoutine) -> SavedRoutine:
    save_saved_routine(body.name, body.code)
    return body


@router.delete(
    "/saved-routines/{name}",
    summary="Delete a saved routine",
    tags=["Routines"],
)
def delete_saved_routine_endpoint(name: str):
    delete_saved_routine(name)
    return {"ok": True}
