from __future__ import annotations

from typing import Iterable, List, Mapping, Optional, Sequence

from .models import GroupLayout, GroupLayoutDivider, GroupLayoutDividers, GroupLayoutItem

DEFAULT_GROUP_LAYOUT_COLUMNS = 4
MAX_GROUP_LAYOUT_COLUMNS = 8


def _unique_member_ids(member_ids: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    unique_ids: List[str] = []
    for panel_id in member_ids:
        if not isinstance(panel_id, str):
            continue
        normalized = panel_id.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique_ids.append(normalized)
    return unique_ids


def _normalize_positive_int(value: object) -> Optional[int]:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return None


def _unique_dividers(
    dividers: Sequence[GroupLayoutDivider],
    max_row: int,
    max_column: int,
) -> List[GroupLayoutDivider]:
    if max_row < 1 or max_column < 1:
        return []

    seen: set[tuple[int, int]] = set()
    result: List[GroupLayoutDivider] = []
    for divider in dividers:
        row = _normalize_positive_int(divider.row)
        column = _normalize_positive_int(divider.column)
        if row is None or column is None:
            continue
        if row > max_row or column > max_column:
            continue
        key = (row, column)
        if key in seen:
            continue
        seen.add(key)
        result.append(GroupLayoutDivider(row=row, column=column))

    return sorted(result, key=lambda divider: (divider.row, divider.column))


def _normalize_dividers(
    dividers: Optional[GroupLayoutDividers],
    rows: int,
    columns: int,
) -> Optional[GroupLayoutDividers]:
    if dividers is None:
        return None

    vertical = _unique_dividers(dividers.vertical, rows, columns - 1)
    horizontal = _unique_dividers(dividers.horizontal, rows - 1, columns)
    if not vertical and not horizontal:
        return None

    return GroupLayoutDividers(vertical=vertical, horizontal=horizontal)


def build_default_group_layout(
    member_ids: Sequence[str],
    columns: int = DEFAULT_GROUP_LAYOUT_COLUMNS,
) -> Optional[GroupLayout]:
    unique_ids = _unique_member_ids(member_ids)
    if not unique_ids:
        return None

    normalized_columns = max(1, min(MAX_GROUP_LAYOUT_COLUMNS, int(columns or DEFAULT_GROUP_LAYOUT_COLUMNS)))
    items: List[GroupLayoutItem] = []
    for index, panel_id in enumerate(unique_ids):
        row = (index // normalized_columns) + 1
        column = (index % normalized_columns) + 1
        items.append(GroupLayoutItem(panel_id=panel_id, row=row, column=column))
    return GroupLayout(columns=normalized_columns, items=items)


def normalize_group_layout(
    member_ids: Sequence[str],
    layout: Optional[GroupLayout | Mapping[str, object]],
) -> Optional[GroupLayout]:
    unique_ids = _unique_member_ids(member_ids)
    if not unique_ids:
        return None

    if layout is None:
        return build_default_group_layout(unique_ids)

    if not isinstance(layout, GroupLayout):
        layout = GroupLayout.model_validate(layout)

    columns = max(1, min(MAX_GROUP_LAYOUT_COLUMNS, int(layout.columns or DEFAULT_GROUP_LAYOUT_COLUMNS)))
    valid_ids = set(unique_ids)
    taken_positions: set[tuple[int, int]] = set()
    positions_by_panel: dict[str, tuple[int, int]] = {}

    for item in layout.items:
        panel_id = item.panel_id.strip()
        if panel_id not in valid_ids or panel_id in positions_by_panel:
            continue

        row = max(1, int(item.row))
        column = max(1, min(columns, int(item.column)))
        while (row, column) in taken_positions:
            column += 1
            if column > columns:
                column = 1
                row += 1

        positions_by_panel[panel_id] = (row, column)
        taken_positions.add((row, column))

    next_row = 1
    next_column = 1

    def next_available_position() -> tuple[int, int]:
        nonlocal next_row, next_column
        while (next_row, next_column) in taken_positions:
            next_column += 1
            if next_column > columns:
                next_column = 1
                next_row += 1
        taken_positions.add((next_row, next_column))
        return next_row, next_column

    items: List[GroupLayoutItem] = []
    for panel_id in unique_ids:
        row, column = positions_by_panel.get(panel_id, next_available_position())
        items.append(GroupLayoutItem(panel_id=panel_id, row=row, column=column))

    minimum_rows = max(1, (len(unique_ids) + columns - 1) // columns, *(item.row for item in items))
    explicit_rows = _normalize_positive_int(layout.rows)
    rows = max(minimum_rows, explicit_rows or minimum_rows)
    dividers = _normalize_dividers(layout.dividers, rows, columns)

    return GroupLayout(
        columns=columns,
        rows=rows if explicit_rows is not None and rows > minimum_rows else None,
        items=items,
        dividers=dividers,
    )
