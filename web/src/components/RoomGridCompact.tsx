import React from "react";
import type { Panel } from "../types";
import { isSkylightPanel, organizePanelsByRoom } from "../utils/panelRooms";
import type { ControlSource } from "../utils/controlManager";

type Props = {
    panels: Panel[];
    transitioning: Set<string>;
    panelControls?: Map<string, ControlSource>;
    highlightedPanelIds?: Set<string>;
};

export default function RoomGridCompact({
    panels,
    transitioning,
    panelControls = new Map(),
    highlightedPanelIds = new Set(),
}: Props) {
    const { room1, room2 } = organizePanelsByRoom(panels);

    const getTintColor = (level: number) => {
        if (level === 0) return "#e8f3ff";
        if (level < 25) return "#9ec5ff";
        if (level < 50) return "#6ba3ff";
        if (level < 75) return "#3d7fd6";
        return "#1e4a8c";
    };

    const renderPanel = (panel: Panel) => {
        const controlSource = panelControls.get(panel.id);
        const controlType = controlSource ? controlSource.type : "manual";
        const showIndicator = controlType !== "manual";
        const isHighlighted = highlightedPanelIds.has(panel.id);

        return (
            <div
                key={panel.id}
                data-testid={`compact-panel-${panel.id}`}
                className={`room-compact-panel ${transitioning.has(panel.id) ? "transitioning" : ""} controlled-${controlType} ${isSkylightPanel(panel) ? "room-compact-skylight-featured" : ""} ${isHighlighted ? "room-compact-panel-selected-group" : ""}`}
                title={controlSource ? `Controlled by: ${controlType}` : panel.name}
            >
                <div className="room-compact-panel-id">{panel.id}</div>
                <div className="room-compact-panel-status" style={{ backgroundColor: getTintColor(panel.level) }}>
                    {panel.level}%
                </div>
                {showIndicator && (
                    <div className={`room-compact-control-indicator ${controlType}`}>
                        {controlType === "group" ? "G" : "R"}
                    </div>
                )}
            </div>
        );
    };

    return (
        <div className="room-grid-compact">
            <section className="room-compact-section" aria-label="Room 1">
                <div className="room-compact-header room-header-unlabeled">
                    <h3 className="visually-hidden">Room 1</h3>
                    <span className="room-compact-count">{room1.length} panels</span>
                </div>
                <div className="room-compact-grid">{room1.map(renderPanel)}</div>
            </section>

            <section className="room-compact-section" aria-label="Room 2">
                <div className="room-compact-header room-header-unlabeled">
                    <h3 className="visually-hidden">Room 2</h3>
                    <span className="room-compact-count">{room2.length} panels</span>
                </div>
                <div className="room-compact-grid">{room2.map(renderPanel)}</div>
            </section>
        </div>
    );
}
