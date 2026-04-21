import { useEffect, useRef, useState } from "react";

import type { GroupLayout, GroupLayoutDivider, GroupLayoutDividers, Panel } from "../types";
import {
    DEFAULT_GROUP_LAYOUT_COLUMNS,
    MAX_GROUP_LAYOUT_COLUMNS,
    layoutItemMap,
    normalizeGroupLayout,
} from "../utils/groupLayout";
import { sortPanelsByNumber } from "../utils/panelSort";

type Props = {
    panels: Panel[];
    selectedPanelIds: Set<string>;
    onTogglePanel: (panelId: string) => void;
    layout: GroupLayout | null;
    onLayoutChange: (layout: GroupLayout | null) => void;
};

type DividerKind = keyof GroupLayoutDividers;

function clampColumns(value: number): number {
    if (!Number.isFinite(value)) return DEFAULT_GROUP_LAYOUT_COLUMNS;
    if (value < 1) return 1;
    if (value > MAX_GROUP_LAYOUT_COLUMNS) return MAX_GROUP_LAYOUT_COLUMNS;
    return Math.floor(value);
}

function dividerKey(divider: GroupLayoutDivider): string {
    return `${divider.row}:${divider.column}`;
}

function getDividers(layout: GroupLayout): GroupLayoutDividers {
    return {
        vertical: layout.dividers?.vertical ?? [],
        horizontal: layout.dividers?.horizontal ?? [],
    };
}

function hasAnyDividers(dividers: GroupLayoutDividers): boolean {
    return dividers.vertical.length > 0 || dividers.horizontal.length > 0;
}

export default function GroupLayoutEditor({
    panels,
    selectedPanelIds,
    onTogglePanel,
    layout,
    onLayoutChange,
}: Props) {
    const sortedPanels = sortPanelsByNumber(panels);
    const selectedIds = sortedPanels.filter(panel => selectedPanelIds.has(panel.id)).map(panel => panel.id);
    const panelById = new Map(sortedPanels.map(panel => [panel.id, panel]));
    const effectiveLayout = normalizeGroupLayout(selectedIds, layout);
    const itemMap = layoutItemMap(effectiveLayout);
    const [columnInputValue, setColumnInputValue] = useState(String(effectiveLayout?.columns ?? DEFAULT_GROUP_LAYOUT_COLUMNS));
    const [draggingPanelId, setDraggingPanelId] = useState<string | null>(null);
    const lastValidColumnsRef = useRef(effectiveLayout?.columns ?? DEFAULT_GROUP_LAYOUT_COLUMNS);

    useEffect(() => {
        const nextColumns = effectiveLayout?.columns ?? DEFAULT_GROUP_LAYOUT_COLUMNS;
        lastValidColumnsRef.current = nextColumns;
        setColumnInputValue(String(nextColumns));
    }, [effectiveLayout?.columns]);

    const updateLayout = (nextLayout: GroupLayout | null) => {
        onLayoutChange(normalizeGroupLayout(selectedIds, nextLayout));
    };

    const commitColumns = (rawValue: string) => {
        const fallback = lastValidColumnsRef.current || DEFAULT_GROUP_LAYOUT_COLUMNS;
        const nextColumns = rawValue.trim() === "" ? fallback : clampColumns(Number(rawValue));
        lastValidColumnsRef.current = nextColumns;
        setColumnInputValue(String(nextColumns));

        if (effectiveLayout) {
            updateLayout({ ...effectiveLayout, columns: nextColumns });
        }
    };

    const handleColumnInputChange = (rawValue: string) => {
        setColumnInputValue(rawValue);
        if (rawValue.trim() === "") return;

        const nextColumns = clampColumns(Number(rawValue));
        lastValidColumnsRef.current = nextColumns;
        setColumnInputValue(String(nextColumns));
        if (effectiveLayout) {
            updateLayout({ ...effectiveLayout, columns: nextColumns });
        }
    };

    const nudgeColumns = (delta: number) => {
        const current = columnInputValue.trim() === ""
            ? (lastValidColumnsRef.current || DEFAULT_GROUP_LAYOUT_COLUMNS)
            : Number(columnInputValue);
        commitColumns(String(clampColumns(current + delta)));
    };

    const movePanelToCell = (panelId: string, row: number, column: number) => {
        if (!effectiveLayout) return;
        const currentItem = itemMap.get(panelId);
        if (!currentItem) return;

        const targetItem = effectiveLayout.items.find(item => item.row === row && item.column === column);
        const items = effectiveLayout.items.map(item => {
            if (item.panel_id === panelId) {
                return { ...item, row, column };
            }

            if (targetItem && item.panel_id === targetItem.panel_id) {
                return { ...item, row: currentItem.row, column: currentItem.column };
            }

            return item;
        });

        updateLayout({ ...effectiveLayout, items });
    };

    const movePanelByKeyboard = (panelId: string, rowDelta: number, columnDelta: number) => {
        if (!effectiveLayout) return;
        const item = itemMap.get(panelId);
        if (!item) return;
        const nextRow = Math.max(1, item.row + rowDelta);
        const nextColumn = Math.max(1, Math.min(effectiveLayout.columns, item.column + columnDelta));
        movePanelToCell(panelId, nextRow, nextColumn);
    };

    const addRow = () => {
        if (!effectiveLayout) return;
        updateLayout({ ...effectiveLayout, rows: rowCount + 1 });
    };

    const updateDividers = (
        kind: DividerKind,
        segments: GroupLayoutDivider[],
        mode: "line" | "single",
    ) => {
        if (!effectiveLayout) return;

        const current = getDividers(effectiveLayout);
        const currentList = current[kind];
        const segmentKeys = new Set(segments.map(dividerKey));
        const currentKeys = new Set(currentList.map(dividerKey));
        const shouldRemove = mode === "single"
            ? segments.every(segment => currentKeys.has(dividerKey(segment)))
            : segments.every(segment => currentKeys.has(dividerKey(segment)));

        const nextList = shouldRemove
            ? currentList.filter(divider => !segmentKeys.has(dividerKey(divider)))
            : [
                ...currentList,
                ...segments.filter(segment => !currentKeys.has(dividerKey(segment))),
            ];
        const nextDividers = { ...current, [kind]: nextList };

        updateLayout({
            ...effectiveLayout,
            dividers: hasAnyDividers(nextDividers) ? nextDividers : undefined,
        });
    };

    const columns = effectiveLayout?.columns ?? DEFAULT_GROUP_LAYOUT_COLUMNS;
    const occupiedRowCount = effectiveLayout
        ? Math.max(
            1,
            Math.ceil(selectedIds.length / columns),
            ...effectiveLayout.items.map(item => item.row),
            effectiveLayout.rows ?? 1,
        )
        : 0;
    const rowCount = occupiedRowCount;
    const gridTemplateColumns = Array.from({ length: Math.max(1, columns * 2 - 1) }, (_, index) =>
        index % 2 === 0 ? "minmax(0, 1fr)" : "20px",
    ).join(" ");
    const gridTemplateRows = Array.from({ length: Math.max(1, rowCount * 2 - 1) }, (_, index) =>
        index % 2 === 0 ? "minmax(82px, auto)" : "20px",
    ).join(" ");
    const verticalDividerKeys = new Set(effectiveLayout?.dividers?.vertical.map(dividerKey) ?? []);
    const horizontalDividerKeys = new Set(effectiveLayout?.dividers?.horizontal.map(dividerKey) ?? []);

    return (
        <>
            <div className="form-group">
                <label>Select Windows ({selectedPanelIds.size} selected)</label>
                <div className="panel-selector">
                    {sortedPanels.map(panel => (
                        <label key={panel.id} className="panel-checkbox">
                            <input
                                type="checkbox"
                                checked={selectedPanelIds.has(panel.id)}
                                onChange={() => onTogglePanel(panel.id)}
                            />
                            <span>{panel.name}</span>
                            <span className="panel-id">{panel.id}</span>
                        </label>
                    ))}
                </div>
            </div>

            {effectiveLayout && (
                <div className="group-layout-editor">
                    <div className="form-group">
                        <label>Layout Columns</label>
                        <input
                            className="group-layout-column-input"
                            type="number"
                            min={1}
                            max={MAX_GROUP_LAYOUT_COLUMNS}
                            step={1}
                            inputMode="numeric"
                            value={columnInputValue}
                            onChange={event => handleColumnInputChange(event.target.value)}
                            onBlur={event => commitColumns(event.target.value)}
                            onKeyDown={event => {
                                if (event.key === "ArrowUp") {
                                    event.preventDefault();
                                    nudgeColumns(1);
                                }
                                if (event.key === "ArrowDown") {
                                    event.preventDefault();
                                    nudgeColumns(-1);
                                }
                                if (event.key === "Enter") {
                                    commitColumns(event.currentTarget.value);
                                }
                            }}
                        />
                        <div className="group-layout-hint">
                            Drag panels to rearrange them. Right-click a panel to remove it. Left-click a divider strip to toggle its full row or column; right-click toggles one strip.
                        </div>
                    </div>

                    <div className="group-layout-preview-wrapper">
                        <div className="group-layout-preview-label">2D Preview</div>
                        <div
                            className="group-layout-preview-grid"
                            style={{
                                gridTemplateColumns,
                                gridTemplateRows,
                            }}
                        >
                            {Array.from({ length: rowCount }).flatMap((_, rowIndex) => {
                                const row = rowIndex + 1;
                                const cells = Array.from({ length: columns }).map((__, columnIndex) => {
                                    const column = columnIndex + 1;
                                    const item = effectiveLayout.items.find(entry => entry.row === row && entry.column === column);
                                    const panel = item ? panelById.get(item.panel_id) : null;

                                    return (
                                        <div
                                            key={`cell-${row}-${column}`}
                                            className={`group-layout-preview-cell ${draggingPanelId ? "drag-active" : ""}`}
                                            style={{ gridColumn: column * 2 - 1, gridRow: row * 2 - 1 }}
                                            onDragOver={event => event.preventDefault()}
                                            onDrop={event => {
                                                event.preventDefault();
                                                const panelId = event.dataTransfer.getData("text/plain") || draggingPanelId;
                                                if (panelId) movePanelToCell(panelId, row, column);
                                                setDraggingPanelId(null);
                                            }}
                                        >
                                            {panel && item && (
                                                <div
                                                    className="group-layout-preview-tile"
                                                    draggable
                                                    tabIndex={0}
                                                    title="Right-click to remove from group, drag to move, or use arrow keys while focused"
                                                    onClick={event => {
                                                        event.stopPropagation();
                                                    }}
                                                    onContextMenu={event => {
                                                        event.preventDefault();
                                                        event.stopPropagation();
                                                        onTogglePanel(panel.id);
                                                    }}
                                                    onDragStart={event => {
                                                        event.dataTransfer.setData("text/plain", panel.id);
                                                        event.dataTransfer.effectAllowed = "move";
                                                        setDraggingPanelId(panel.id);
                                                    }}
                                                    onDragEnd={() => setDraggingPanelId(null)}
                                                    onKeyDown={event => {
                                                        if (event.key === "ArrowUp") {
                                                            event.preventDefault();
                                                            movePanelByKeyboard(panel.id, -1, 0);
                                                        }
                                                        if (event.key === "ArrowDown") {
                                                            event.preventDefault();
                                                            movePanelByKeyboard(panel.id, 1, 0);
                                                        }
                                                        if (event.key === "ArrowLeft") {
                                                            event.preventDefault();
                                                            movePanelByKeyboard(panel.id, 0, -1);
                                                        }
                                                        if (event.key === "ArrowRight") {
                                                            event.preventDefault();
                                                            movePanelByKeyboard(panel.id, 0, 1);
                                                        }
                                                    }}
                                                >
                                                    <div className="group-layout-preview-name">{panel.name}</div>
                                                    <div className="group-layout-preview-id">{panel.id}</div>
                                                </div>
                                            )}
                                        </div>
                                    );
                                });

                                const verticalDividers = Array.from({ length: Math.max(0, columns - 1) }).map((__, columnIndex) => {
                                    const column = columnIndex + 1;
                                    const divider = { row, column };
                                    const isActive = verticalDividerKeys.has(dividerKey(divider));

                                    return (
                                        <button
                                            key={`vertical-divider-${row}-${column}`}
                                            type="button"
                                            className={`group-layout-divider-strip vertical ${isActive ? "active" : ""}`}
                                            style={{ gridColumn: column * 2, gridRow: row * 2 - 1 }}
                                            aria-pressed={isActive}
                                            title="Left-click toggles this column divider for every row. Right-click toggles this strip only."
                                            onClick={event => {
                                                event.preventDefault();
                                                updateDividers(
                                                    "vertical",
                                                    Array.from({ length: rowCount }).map((___, lineRowIndex) => ({
                                                        row: lineRowIndex + 1,
                                                        column,
                                                    })),
                                                    "line",
                                                );
                                            }}
                                            onContextMenu={event => {
                                                event.preventDefault();
                                                updateDividers("vertical", [divider], "single");
                                            }}
                                        />
                                    );
                                });

                                if (row >= rowCount) return [...cells, ...verticalDividers];

                                const horizontalDividers = Array.from({ length: columns }).map((__, columnIndex) => {
                                    const row = rowIndex + 1;
                                    const column = columnIndex + 1;
                                    const divider = { row, column };
                                    const isActive = horizontalDividerKeys.has(dividerKey(divider));

                                    return (
                                        <button
                                            key={`horizontal-divider-${row}-${column}`}
                                            type="button"
                                            className={`group-layout-divider-strip horizontal ${isActive ? "active" : ""}`}
                                            style={{ gridColumn: column * 2 - 1, gridRow: row * 2 }}
                                            aria-pressed={isActive}
                                            title="Left-click toggles this row divider for every column. Right-click toggles this strip only."
                                            onClick={event => {
                                                event.preventDefault();
                                                updateDividers(
                                                    "horizontal",
                                                    Array.from({ length: columns }).map((___, lineColumnIndex) => ({
                                                        row,
                                                        column: lineColumnIndex + 1,
                                                    })),
                                                    "line",
                                                );
                                            }}
                                            onContextMenu={event => {
                                                event.preventDefault();
                                                updateDividers("horizontal", [divider], "single");
                                            }}
                                        />
                                    );
                                });

                                return [...cells, ...verticalDividers, ...horizontalDividers];
                            })}
                        </div>
                        <button
                            type="button"
                            className="group-layout-add-row-btn"
                            onClick={addRow}
                        >
                            Add Row
                        </button>
                    </div>
                </div>
            )}
        </>
    );
}
