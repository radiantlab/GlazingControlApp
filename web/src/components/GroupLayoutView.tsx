import type { Group, Panel } from "../types";
import type { ControlSource } from "../utils/controlManager";
import { layoutItemMap, normalizeGroupLayout } from "../utils/groupLayout";

import PanelTile from "./PanelTile";

type Props = {
    panels: Panel[];
    groups: Group[];
    onSet: (panelId: string, level: number) => Promise<void>;
    busyId?: string | null;
    transitioning?: Set<string>;
    panelControls?: Map<string, ControlSource>;
    emptyMessage?: string;
};

function dividerKey(row: number, column: number): string {
    return `${row}:${column}`;
}

function gridTemplateTrackList(
    count: number,
    boundaryIndexes: Set<number>,
    dividerGap: string,
    baseGap: string,
    itemTrack: string,
): string {
    const tracks: string[] = [];
    for (let index = 1; index <= count; index += 1) {
        tracks.push(itemTrack);
        if (index < count) {
            tracks.push(boundaryIndexes.has(index) ? dividerGap : baseGap);
        }
    }
    return tracks.join(" ");
}

export default function GroupLayoutView({
    panels,
    groups,
    onSet,
    busyId,
    transitioning = new Set(),
    panelControls = new Map(),
    emptyMessage = "No groups are available yet. Create a group to use the 2D layout view.",
}: Props) {
    const panelsById = new Map(panels.map(panel => [panel.id, panel]));
    const visibleGroups = [...groups]
        .filter(group => group.member_ids.length > 0)
        .sort((a, b) => a.name.localeCompare(b.name));

    return (
        <div className="room-grid-container">
            <div className="group-layout-sections">
                {visibleGroups.map(group => {
                    const layout = normalizeGroupLayout(group.member_ids, group.layout);
                    const itemMap = layoutItemMap(layout);
                    const groupPanels = group.member_ids
                        .map(panelId => panelsById.get(panelId))
                        .filter((panel): panel is Panel => Boolean(panel));

                    if (!groupPanels.length || !layout) {
                        return null;
                    }

                    const verticalDividers = layout.dividers?.vertical ?? [];
                    const horizontalDividers = layout.dividers?.horizontal ?? [];
                    const rowCount = Math.max(
                        1,
                        layout.rows ?? 1,
                        ...layout.items.map(item => item.row),
                        ...verticalDividers.map(divider => divider.row),
                        ...horizontalDividers.map(divider => divider.row + 1),
                    );
                    const hasDividers = Boolean(verticalDividers.length || horizontalDividers.length);
                    const verticalDividerKeys = new Set(verticalDividers.map(divider => dividerKey(divider.row, divider.column)));
                    const horizontalDividerKeys = new Set(horizontalDividers.map(divider => dividerKey(divider.row, divider.column)));
                    const dividerColumnBoundaries = new Set(verticalDividers.map(divider => divider.column));
                    const dividerRowBoundaries = new Set(horizontalDividers.map(divider => divider.row));
                    const gridTemplateColumns = hasDividers
                        ? gridTemplateTrackList(layout.columns, dividerColumnBoundaries, "50px", "16px", "minmax(0, 1fr)")
                        : `repeat(${layout.columns}, minmax(0, 1fr))`;
                    const gridTemplateRows = hasDividers
                        ? gridTemplateTrackList(rowCount, dividerRowBoundaries, "50px", "16px", "auto")
                        : undefined;
                    const dividerIntersections = Array.from({ length: Math.max(0, rowCount - 1) }).flatMap((_, rowIndex) => {
                        const row = rowIndex + 1;
                        return Array.from({ length: Math.max(0, layout.columns - 1) }).map((__, columnIndex) => {
                            const column = columnIndex + 1;
                            const verticalAbove = verticalDividerKeys.has(dividerKey(row, column));
                            const verticalBelow = verticalDividerKeys.has(dividerKey(row + 1, column));
                            const horizontalLeft = horizontalDividerKeys.has(dividerKey(row, column));
                            const horizontalRight = horizontalDividerKeys.has(dividerKey(row, column + 1));
                            const touchesVertical = verticalAbove || verticalBelow;
                            const touchesHorizontal = horizontalLeft || horizontalRight;

                            if (touchesVertical && touchesHorizontal) {
                                return { row, column, orientation: "horizontal" as const };
                            }
                            if (verticalAbove && verticalBelow) {
                                return { row, column, orientation: "vertical" as const };
                            }
                            if (horizontalLeft && horizontalRight) {
                                return { row, column, orientation: "horizontal" as const };
                            }
                            return null;
                        });
                    }).filter((intersection): intersection is { row: number; column: number; orientation: "horizontal" | "vertical" } => Boolean(intersection));

                    return (
                        <div key={group.id} className="room-section group-layout-section">
                            <div className="room-header">
                                <div>
                                    <h2 className="room-title">{group.name}</h2>
                                    <div className="group-layout-subtitle">{group.id}</div>
                                </div>
                                <div className="room-stats">
                                    <span>{groupPanels.length} windows</span>
                                    <span>{layout.columns} columns</span>
                                </div>
                            </div>

                            <div
                                className={`group-layout-grid ${hasDividers ? "with-dividers" : ""}`}
                                style={{ gridTemplateColumns, gridTemplateRows }}
                            >
                                {groupPanels.map(panel => {
                                    const item = itemMap.get(panel.id);
                                    if (!item) return null;

                                    return (
                                        <div
                                            key={`${group.id}-${panel.id}`}
                                            className="group-layout-cell"
                                            style={{
                                                gridColumn: hasDividers ? item.column * 2 - 1 : item.column,
                                                gridRow: hasDividers ? item.row * 2 - 1 : item.row,
                                            }}
                                        >
                                            <PanelTile
                                                panel={panel}
                                                onSet={onSet}
                                                busyId={busyId}
                                                isTransitioning={transitioning.has(panel.id)}
                                                controlSource={panelControls.get(panel.id)}
                                            />
                                        </div>
                                    );
                                })}
                                {hasDividers && verticalDividers.map(divider => (
                                    <div
                                        key={`vertical-${dividerKey(divider.row, divider.column)}`}
                                        className="group-layout-view-divider vertical"
                                        style={{ gridColumn: divider.column * 2, gridRow: divider.row * 2 - 1 }}
                                    />
                                ))}
                                {hasDividers && horizontalDividers.map(divider => (
                                    <div
                                        key={`horizontal-${dividerKey(divider.row, divider.column)}`}
                                        className="group-layout-view-divider horizontal"
                                        style={{ gridColumn: divider.column * 2 - 1, gridRow: divider.row * 2 }}
                                    />
                                ))}
                                {hasDividers && dividerIntersections.map(intersection => (
                                    <div
                                        key={`intersection-${intersection.orientation}-${dividerKey(intersection.row, intersection.column)}`}
                                        className={`group-layout-view-divider intersection ${intersection.orientation}`}
                                        style={{ gridColumn: intersection.column * 2, gridRow: intersection.row * 2 }}
                                    />
                                ))}
                            </div>
                        </div>
                    );
                })}

                {!visibleGroups.length && (
                    <div className="room-section">
                        <div className="group-layout-empty">
                            {emptyMessage}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
