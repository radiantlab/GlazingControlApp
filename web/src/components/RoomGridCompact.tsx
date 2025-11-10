import React from "react";
import type { Panel } from "../api";
import type { ControlSource } from "../utils/controlManager";

type Props = {
    panels: Panel[];
    transitioning: Set<string>;
    panelControls?: Map<string, ControlSource>;
};

// Simplified compact view for when side panel is open
export default function RoomGridCompact({ panels, transitioning, panelControls = new Map() }: Props) {
    // Organize panels by room (same logic as RoomGrid but simplified display)
    const room1Panels = panels.filter(p => {
        if (p.id === 'SK1') return true;
        if (p.id.startsWith('P')) {
            const num = parseInt(p.id.replace('P', ''));
            return num >= 1 && num <= 9;
        }
        return false;
    });
    const room2Panels = panels.filter(p => {
        if (p.id === 'SK2') return true;
        if (p.id.startsWith('P')) {
            const num = parseInt(p.id.replace('P', ''));
            return num >= 10 && num <= 18;
        }
        return false;
    });

    // Sort to put skylights first
    const sortPanels = (a: Panel, b: Panel) => {
        const aIsSkylight = a.id.startsWith('SK');
        const bIsSkylight = b.id.startsWith('SK');
        if (aIsSkylight && !bIsSkylight) return -1; // Skylights first
        if (!aIsSkylight && bIsSkylight) return 1;
        return a.id.localeCompare(b.id);
    };

    const room1 = [...room1Panels].sort(sortPanels);
    const room2 = [...room2Panels].sort(sortPanels);

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
                    <h3>Room 1</h3>
                    <span className="room-compact-count">{room1.length} panels</span>
                </div>
                <div className="room-compact-grid">
                    {room1.map((panel, index) => {
                        const controlSource = panelControls.get(panel.id);
                        // Default to manual if no control source
                        const controlType = controlSource ? controlSource.type : 'manual';
                        const getControlClass = () => `controlled-${controlType}`;
                        const isSkylight = panel.id.startsWith('SK');
                        const isFirstSkylight = isSkylight && index === 0;
                        
                        return (
                            <div
                                key={panel.id}
                                className={`room-compact-panel ${transitioning.has(panel.id) ? 'transitioning' : ''} ${getControlClass()} ${isFirstSkylight ? 'room-compact-skylight-featured' : ''}`}
                                title={controlSource ? `Controlled by: ${controlType}` : `Available for: ${controlType} control`}
                            >
                                <div className="room-compact-panel-id">{panel.id}</div>
                                <div
                                    className="room-compact-panel-status"
                                    style={{ backgroundColor: getTintColor(panel.level) }}
                                >
                                    {panel.level}%
                                </div>
                                <div className={`room-compact-control-indicator ${controlType}`}>
                                    {controlType === 'manual' ? '✋' : controlType === 'group' ? '▣' : '⚙'}
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>

            <div className="room-compact-section">
                <div className="room-compact-header">
                    <h3>Room 2</h3>
                    <span className="room-compact-count">{room2.length} panels</span>
                </div>
                <div className="room-compact-grid">
                    {room2.map((panel, index) => {
                        const controlSource = panelControls.get(panel.id);
                        // Default to manual if no control source
                        const controlType = controlSource ? controlSource.type : 'manual';
                        const getControlClass = () => `controlled-${controlType}`;
                        const isSkylight = panel.id.startsWith('SK');
                        const isFirstSkylight = isSkylight && index === 0;
                        
                        return (
                            <div
                                key={panel.id}
                                className={`room-compact-panel ${transitioning.has(panel.id) ? 'transitioning' : ''} ${getControlClass()} ${isFirstSkylight ? 'room-compact-skylight-featured' : ''}`}
                                title={controlSource ? `Controlled by: ${controlType}` : `Available for: ${controlType} control`}
                            >
                                <div className="room-compact-panel-id">{panel.id}</div>
                                <div
                                    className="room-compact-panel-status"
                                    style={{ backgroundColor: getTintColor(panel.level) }}
                                >
                                    {panel.level}%
                                </div>
                                <div className={`room-compact-control-indicator ${controlType}`}>
                                    {controlType === 'manual' ? '✋' : controlType === 'group' ? '▣' : '⚙'}
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}

