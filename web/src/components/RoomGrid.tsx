import React, { useState } from "react";
import type { Panel } from "../api";
import type { ControlSource } from "../utils/controlManager";

type Props = {
    panels: Panel[];
    onSet: (panelId: string, level: number) => Promise<void>;
    busyId?: string | null;
    transitioning?: Set<string>;
    panelControls?: Map<string, ControlSource>;
};

// Organize panels by room
// Room 1: P01-P09 (9 walls) + SK1 (skylight) = 10 panels
// Room 2: P10-P18 (9 walls) + SK2 (skylight) = 10 panels
// Total: 18 wall panels + 2 skylights = 20 panels
function organizePanels(panels: Panel[]) {
    const room1: Panel[] = [];
    const room2: Panel[] = [];

    panels.forEach(panel => {
        if (panel.id.startsWith('SK')) {
            if (panel.id === 'SK1') {
                room1.push(panel);
            } else if (panel.id === 'SK2') {
                room2.push(panel);
            }
        } else if (panel.id.startsWith('P')) {
            const panelNum = parseInt(panel.id.replace('P', ''));
            if (panelNum >= 1 && panelNum <= 9) {
                room1.push(panel);
            } else if (panelNum >= 10 && panelNum <= 18) {
                room2.push(panel);
            }
            // Any panel outside P01-P18 will be ignored
        }
    });

    // Sort by ID for consistent ordering (but keep skylights at start)
    const sortPanels = (a: Panel, b: Panel) => {
        const aIsSkylight = a.id.startsWith('SK');
        const bIsSkylight = b.id.startsWith('SK');
        if (aIsSkylight && !bIsSkylight) return -1; // Skylights first
        if (!aIsSkylight && bIsSkylight) return 1;
        return a.id.localeCompare(b.id);
    };
    room1.sort(sortPanels);
    room2.sort(sortPanels);

    return { room1, room2 };
}

function PanelTile({ panel, onSet, busyId, isTransitioning, controlSource, className }: { panel: Panel; onSet: (id: string, level: number) => Promise<void>; busyId?: string | null; isTransitioning?: boolean; controlSource?: ControlSource | null; className?: string }) {
    const [localLevel, setLocalLevel] = useState(panel.level);
    const isSkylight = panel.id.startsWith('SK');
    
    // Sync local level when panel prop updates
    React.useEffect(() => {
        setLocalLevel(panel.level);
    }, [panel.level]);
    
    // Color based on tint level (0 = clear, 100 = dark)
    const getTintColor = (level: number) => {
        if (level === 0) return '#e8f3ff'; // Clear/light blue
        if (level < 25) return '#9ec5ff';
        if (level < 50) return '#6ba3ff';
        if (level < 75) return '#3d7fd6';
        return '#1e4a8c'; // Dark blue
    };

    const isBusy = busyId === panel.id;

    const getControlBadge = () => {
        // If no control source, show manual (default state)
        if (!controlSource) {
            return { label: 'Manual', class: 'control-badge-manual', icon: '✋' };
        }
        
        switch (controlSource.type) {
            case 'manual':
                return { label: 'Manual', class: 'control-badge-manual', icon: '✋' };
            case 'group':
                return { label: 'Group', class: 'control-badge-group', icon: '▣' };
            case 'routine':
                return { label: 'Routine', class: 'control-badge-routine', icon: '⚙' };
        }
    };

    const badge = getControlBadge();

    // Determine border color based on control source (default to manual)
    const getControlBorderClass = () => {
        if (!controlSource) return 'panel-controlled-manual';
        return `panel-controlled-${controlSource.type}`;
    };

    return (
        <div className={`panel-tile ${isSkylight ? 'panel-tile-skylight' : ''} ${isBusy ? 'panel-tile-busy' : ''} ${isTransitioning ? 'panel-tile-transitioning' : ''} ${getControlBorderClass()} ${className || ''}`}>
            <div className="panel-tile-header">
                <div className="panel-tile-name">{panel.name}</div>
                <div className="panel-tile-header-right">
                    <div className={`control-badge ${badge.class}`} title={controlSource ? `Controlled by: ${badge.label}` : `Available for: ${badge.label} control`}>
                        <span className="control-badge-icon">{badge.icon}</span>
                        <span className="control-badge-label">{badge.label}</span>
                    </div>
                    <div className="panel-tile-id">{panel.id}</div>
                </div>
            </div>
            
            <div className="panel-tile-status">
                <div className="panel-tile-level-display" style={{ backgroundColor: getTintColor(localLevel) }}>
                    <span className="panel-tile-level-value">{localLevel}%</span>
                    {isTransitioning && (
                        <div className="panel-tile-transition-indicator">
                            <div className="panel-tile-transition-spinner"></div>
                            <span className="panel-tile-transition-label">Transitioning...</span>
                        </div>
                    )}
                </div>
            </div>

            <div className="panel-tile-controls">
                <div className="panel-tile-slider-wrapper">
                    <input
                        type="range"
                        min={0}
                        max={100}
                        value={localLevel}
                        disabled={isBusy}
                        onChange={(e) => {
                            const val = Number(e.target.value);
                            setLocalLevel(val);
                        }}
                        className="panel-tile-slider"
                    />
                </div>

                <div className="panel-tile-quick-controls">
                    {[0, 25, 50, 75, 100].map(v => (
                        <button
                            key={v}
                            className="panel-tile-quick-btn"
                            disabled={isBusy}
                            onClick={async () => {
                                setLocalLevel(v);
                                await onSet(panel.id, v);
                            }}
                        >
                            {v}
                        </button>
                    ))}
                </div>

                <button
                    className="panel-tile-apply-btn"
                    disabled={isBusy || localLevel === panel.level}
                    onClick={async () => await onSet(panel.id, localLevel)}
                >
                    {isBusy ? "..." : localLevel === panel.level ? "✓" : "Apply"}
                </button>
            </div>
        </div>
    );
}

export default function RoomGrid({ panels, onSet, busyId, transitioning = new Set(), panelControls = new Map() }: Props) {
    const { room1, room2 } = organizePanels(panels);

    return (
        <div className="room-grid-container">
            <div className="rooms-layout">
                {/* Room 1 */}
                <div className="room-section">
                    <div className="room-header">
                        <h2 className="room-title">Room 1</h2>
                        <div className="room-stats">
                            <span>{room1.length} panels</span>
                        </div>
                    </div>
                    <div className="room-panels-grid">
                        {/* Skylight displayed prominently at top, centered */}
                        {room1.filter(p => p.id.startsWith('SK')).map(panel => (
                            <PanelTile key={panel.id} panel={panel} onSet={onSet} busyId={busyId} isTransitioning={transitioning.has(panel.id)} controlSource={panelControls.get(panel.id)} className="panel-tile-skylight-featured" />
                        ))}
                        {/* Wall panels in a 3x3 grid layout */}
                        {room1.filter(p => !p.id.startsWith('SK')).map(panel => (
                            <PanelTile key={panel.id} panel={panel} onSet={onSet} busyId={busyId} isTransitioning={transitioning.has(panel.id)} controlSource={panelControls.get(panel.id)} />
                        ))}
                    </div>
                </div>

                {/* Room 2 */}
                <div className="room-section">
                    <div className="room-header">
                        <h2 className="room-title">Room 2</h2>
                        <div className="room-stats">
                            <span>{room2.length} panels</span>
                        </div>
                    </div>
                    <div className="room-panels-grid">
                        {/* Skylight displayed prominently at top, centered */}
                        {room2.filter(p => p.id.startsWith('SK')).map(panel => (
                            <PanelTile key={panel.id} panel={panel} onSet={onSet} busyId={busyId} isTransitioning={transitioning.has(panel.id)} controlSource={panelControls.get(panel.id)} className="panel-tile-skylight-featured" />
                        ))}
                        {/* Wall panels in a 3x3 grid layout */}
                        {room2.filter(p => !p.id.startsWith('SK')).map(panel => (
                            <PanelTile key={panel.id} panel={panel} onSet={onSet} busyId={busyId} isTransitioning={transitioning.has(panel.id)} controlSource={panelControls.get(panel.id)} />
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
}

