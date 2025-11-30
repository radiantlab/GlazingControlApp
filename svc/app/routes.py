from __future__ import annotations
from fastapi import APIRouter, HTTPException, Depends, status, Query
from fastapi.responses import Response
from .models import (
    Panel, Group, CommandRequest, CommandResult, GroupCreate, GroupUpdate, 
    AuditEntry, HealthResponse, DeleteGroupResponse, ErrorResponse
)
from typing import List, Optional
import csv
import io
from datetime import datetime, timezone
from .service import ControlService
from .config import MODE
from .state import fetch_audit_entries



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
    result_filter: Optional[str] = Query(None, description="Filter by result text")
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
        result_filter
    )
    
    if has_filters:
        # Filters require fetching all entries to find matches across the full range
        # Use a very high limit to get all entries (practical maximum for exports)
        rows = fetch_audit_entries(limit=1000000, offset=0)
    else:
        # No filters, safe to apply limit upfront for performance
        rows = fetch_audit_entries(limit=limit, offset=0)
    
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
    filename = f"audit_logs_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
