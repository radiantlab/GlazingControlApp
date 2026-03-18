import React from "react";
import type { Panel } from "../types";
import type { ControlSource } from "../utils/controlManager";

type Props = {
    panels: Panel[];
    transitioning: Set<string>;
    panelControls?: Map<string, ControlSource>;
};

// Simplified compact view for when side panel is open
export default function RoomGridCompact({ panels, transitioning, panelControls = new Map() }: Props) {
    const sortedPanels = [...panels].sort((a, b) => a.name.localeCompare(b.name));

    const getTintColor = (level: number) => {
        if (level === 0) return '#e8f3ff';
        if (level < 25) return '#9ec5ff';
        if (level < 50) return '#6ba3ff';
        if (level < 75) return '#3d7fd6';
        return '#1e4a8c';
    };

    return (
        <div className="room-grid-compact">
            <div className="room-compact-section">
                <div className="room-compact-header">
                    <h3>Windows</h3>
                    <span className="room-compact-count">{sortedPanels.length} windows</span>
                </div>
                <div className="room-compact-grid">
                    {sortedPanels.map((panel) => {
                        const controlSource = panelControls.get(panel.id);
                        const controlType = controlSource ? controlSource.type : 'manual';
                        const getControlClass = () => `controlled-${controlType}`;
                        const showIndicator = controlType !== 'manual';
                        const isSkylight = panel.name.toUpperCase().includes('SK') || panel.id.startsWith('SK');
                        
                        return (
                            <div
                                key={panel.id}
                                className={`room-compact-panel ${transitioning.has(panel.id) ? 'transitioning' : ''} ${getControlClass()} ${isSkylight ? 'room-compact-skylight-featured' : ''}`}
                                title={controlSource ? `Controlled by: ${controlType}` : panel.name}
                            >
                                <div className="room-compact-panel-id">{panel.id}</div>
                                <div
                                    className="room-compact-panel-status"
                                    style={{ backgroundColor: getTintColor(panel.level) }}
                                >
                                    {panel.level}%
                                </div>
                                {showIndicator && (
                                    <div className={`room-compact-control-indicator ${controlType}`}>
                                        {controlType === 'group' ? '▣' : '⚙'}
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}

