import type { GroupLayout, GroupLayoutDivider, GroupLayoutDividers, GroupLayoutItem } from "../types";

export const DEFAULT_GROUP_LAYOUT_COLUMNS = 4;
export const MAX_GROUP_LAYOUT_COLUMNS = 8;

function uniquePanelIds(panelIds: string[]): string[] {
    const seen = new Set<string>();
    const uniqueIds: string[] = [];
    for (const panelId of panelIds) {
        const normalized = panelId.trim();
        if (!normalized || seen.has(normalized)) continue;
        seen.add(normalized);
        uniqueIds.push(normalized);
    }
    return uniqueIds;
}

function normalizeColumns(columns?: number | null): number {
    return Math.max(1, Math.min(MAX_GROUP_LAYOUT_COLUMNS, Math.floor(columns || DEFAULT_GROUP_LAYOUT_COLUMNS)));
}

function normalizePositiveInteger(value: number | null | undefined): number | null {
    if (!Number.isFinite(value ?? NaN)) return null;
    return Math.max(1, Math.floor(value as number));
}

function uniqueDividers(
    dividers: GroupLayoutDivider[] | undefined,
    maxRow: number,
    maxColumn: number,
): GroupLayoutDivider[] {
    if (!dividers?.length || maxRow < 1 || maxColumn < 1) return [];

    const seen = new Set<string>();
    const result: GroupLayoutDivider[] = [];
    for (const divider of dividers) {
        const row = normalizePositiveInteger(divider.row);
        const column = normalizePositiveInteger(divider.column);
        if (row == null || column == null || row > maxRow || column > maxColumn) continue;

        const key = `${row}:${column}`;
        if (seen.has(key)) continue;
        seen.add(key);
        result.push({ row, column });
    }

    return result.sort((a, b) => a.row - b.row || a.column - b.column);
}

function normalizeDividers(
    dividers: GroupLayoutDividers | null | undefined,
    rows: number,
    columns: number,
): GroupLayoutDividers | undefined {
    const vertical = uniqueDividers(dividers?.vertical, rows, columns - 1);
    const horizontal = uniqueDividers(dividers?.horizontal, rows - 1, columns);
    if (!vertical.length && !horizontal.length) return undefined;
    return { vertical, horizontal };
}

export function buildDefaultGroupLayout(
    panelIds: string[],
    columns = DEFAULT_GROUP_LAYOUT_COLUMNS,
): GroupLayout | null {
    const uniqueIds = uniquePanelIds(panelIds);
    if (!uniqueIds.length) return null;

    const normalizedColumns = normalizeColumns(columns);
    return {
        columns: normalizedColumns,
        items: uniqueIds.map((panelId, index) => ({
            panel_id: panelId,
            row: Math.floor(index / normalizedColumns) + 1,
            column: (index % normalizedColumns) + 1,
        })),
    };
}

export function normalizeGroupLayout(
    panelIds: string[],
    layout?: GroupLayout | null,
): GroupLayout | null {
    const uniqueIds = uniquePanelIds(panelIds);
    if (!uniqueIds.length) return null;
    if (!layout) return buildDefaultGroupLayout(uniqueIds);

    const columns = normalizeColumns(layout.columns);
    const validIds = new Set(uniqueIds);
    const positions = new Map<string, { row: number; column: number }>();
    const occupied = new Set<string>();

    for (const item of layout.items) {
        const panelId = item.panel_id.trim();
        if (!validIds.has(panelId) || positions.has(panelId)) continue;

        let row = Math.max(1, Math.floor(item.row || 1));
        let column = Math.max(1, Math.min(columns, Math.floor(item.column || 1)));
        while (occupied.has(`${row}:${column}`)) {
            column += 1;
            if (column > columns) {
                column = 1;
                row += 1;
            }
        }

        positions.set(panelId, { row, column });
        occupied.add(`${row}:${column}`);
    }

    let nextRow = 1;
    let nextColumn = 1;
    const nextAvailablePosition = () => {
        while (occupied.has(`${nextRow}:${nextColumn}`)) {
            nextColumn += 1;
            if (nextColumn > columns) {
                nextColumn = 1;
                nextRow += 1;
            }
        }
        occupied.add(`${nextRow}:${nextColumn}`);
        return { row: nextRow, column: nextColumn };
    };

    const items: GroupLayoutItem[] = uniqueIds.map(panelId => {
        const position = positions.get(panelId) ?? nextAvailablePosition();
        return {
            panel_id: panelId,
            row: position.row,
            column: position.column,
        };
    });

    const minimumRows = Math.max(
        1,
        Math.ceil(uniqueIds.length / columns),
        ...items.map(item => item.row),
    );
    const explicitRows = normalizePositiveInteger(layout.rows);
    const rows = Math.max(minimumRows, explicitRows ?? minimumRows);
    const dividers = normalizeDividers(layout.dividers, rows, columns);
    const normalizedLayout: GroupLayout = { columns, items };

    if (explicitRows != null && rows > minimumRows) {
        normalizedLayout.rows = rows;
    }
    if (dividers) {
        normalizedLayout.dividers = dividers;
    }

    return normalizedLayout;
}

export function layoutItemMap(layout?: GroupLayout | null): Map<string, GroupLayoutItem> {
    return new Map((layout?.items || []).map(item => [item.panel_id, item]));
}
