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

// Format timestamp as relative time (e.g., "2 minutes ago", "Just now")
function formatLastUpdated(timestamp: number, currentTime?: number): string {
    if (!timestamp || timestamp === 0) {
        return "Never";
    }
    
    const now = currentTime || (Date.now() / 1000); // Use provided currentTime or get current
    const diff = now - timestamp;
    
    if (diff < 5) {
        return "Just now";
    } else if (diff < 60) {
        const seconds = Math.floor(diff);
        return `${seconds} second${seconds !== 1 ? 's' : ''} ago`;
    } else if (diff < 3600) {
        const minutes = Math.floor(diff / 60);
        return `${minutes} minute${minutes !== 1 ? 's' : ''} ago`;
    } else if (diff < 86400) {
        const hours = Math.floor(diff / 3600);
        return `${hours} hour${hours !== 1 ? 's' : ''} ago`;
    } else {
        const days = Math.floor(diff / 86400);
        return `${days} day${days !== 1 ? 's' : ''} ago`;
    }
}

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

function PanelTile({
    panel,
    onSet,
    busyId,
    isTransitioning,
    controlSource,
    className
}: {
    panel: Panel
    onSet: (id: string, level: number) => Promise<void>
    busyId?: string | null
    isTransitioning?: boolean
    controlSource?: ControlSource | null
    className?: string
}) {
    const [localLevel, setLocalLevel] = React.useState(panel.level)
    const [currentTime, setCurrentTime] = React.useState(Date.now() / 1000)
    const [isInteracting, setIsInteracting] = React.useState(false)
    const interactionTimeoutRef = React.useRef<number | null>(null)
    const isSkylight = panel.id.startsWith('SK')

    // sync localLevel when panel prop updates, but only when the user is not interacting
    React.useEffect(() => {
        if (!isInteracting) {
            setLocalLevel(panel.level)
        }
    }, [panel.level, isInteracting])

    // When operation completes (busyId changes from panel.id to null),
    // verify localLevel matches actual panel.level and reset if needed
    React.useEffect(() => {
        if (busyId !== panel.id && localLevel !== panel.level && !isInteracting) {
            setLocalLevel(panel.level)
        }
    }, [busyId, panel.id, panel.level, localLevel, isInteracting])

    // Update timestamp display every 10 seconds
    React.useEffect(() => {
        const interval = setInterval(() => {
            setCurrentTime(Date.now() / 1000)
        }, 10000)
        return () => clearInterval(interval)
    }, [])

    // cleanup interaction timeout on unmount
    React.useEffect(() => {
        return () => {
            if (interactionTimeoutRef.current) {
                window.clearTimeout(interactionTimeoutRef.current)
                interactionTimeoutRef.current = null
            }
        }
    }, [])

    const getTintColor = (level: number) => {
        if (level === 0) return '#e8f3ff'
        if (level < 25) return '#9ec5ff'
        if (level < 50) return '#6ba3ff'
        if (level < 75) return '#3d7fd6'
        return '#1e4a8c'
    }

    const getTextColor = (level: number) => {
        return level < 50 ? '#1e293b' : '#ffffff'
    }

    const isBusy = busyId === panel.id

    const getControlBadge = () => {
        if (!controlSource) return { label: 'Manual', class: 'control-badge-manual', icon: '✋' }
        switch (controlSource.type) {
            case 'manual':
                return { label: 'Manual', class: 'control-badge-manual', icon: '✋' }
            case 'group':
                return { label: 'Group', class: 'control-badge-group', icon: '▣' }
            case 'routine':
                return { label: 'Routine', class: 'control-badge-routine', icon: '⚙' }
        }
    }

    const badge = getControlBadge()

    const getControlBorderClass = () => {
        if (!controlSource) return 'panel-controlled-manual'
        return `panel-controlled-${controlSource.type}`
    }

    // helper to read the current value from the DOM slider
    const readSliderValue = () => {
        const el = document.getElementById(`range-${panel.id}`) as HTMLInputElement | null
        if (!el) return panel.level
        const v = Number(el.value)
        return Number.isNaN(v) ? panel.level : Math.max(0, Math.min(100, v))
    }

    // pointer handlers to mark the user as interacting
    const startInteraction = () => {
        if (interactionTimeoutRef.current) {
            window.clearTimeout(interactionTimeoutRef.current)
            interactionTimeoutRef.current = null
        }
        setIsInteracting(true)
    }

    const endInteractionDebounced = () => {
        if (interactionTimeoutRef.current) {
            window.clearTimeout(interactionTimeoutRef.current)
        }
        // small delay after pointer up so quick flicks don't cause immediate re-sync
        interactionTimeoutRef.current = window.setTimeout(() => {
            interactionTimeoutRef.current = null
            setIsInteracting(false)
        }, 600)
    }

    return (
        <div
            className={`panel-tile ${isSkylight ? 'panel-tile-skylight' : ''} ${isBusy ? 'panel-tile-busy' : ''} ${isTransitioning ? 'panel-tile-transitioning' : ''} ${getControlBorderClass()} ${className || ''}`}
        >
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
                    <span className="panel-tile-level-value" style={{ color: getTextColor(localLevel) }}>{localLevel}%</span>
                    {isTransitioning && (
                        <div className="panel-tile-transition-indicator">
                            <div className="panel-tile-transition-spinner" />
                            <span className="panel-tile-transition-label">Transitioning...</span>
                        </div>
                    )}
                </div>
                <div className="panel-tile-timestamp">
                    <span className="panel-tile-timestamp-label">Updated:</span>
                    <span className="panel-tile-timestamp-value">{formatLastUpdated(panel.last_change_ts, currentTime)}</span>
                </div>
            </div>

            <div className="panel-tile-controls">
                <div className="panel-tile-slider-wrapper">
                    <input
                        type="range"
                        min={0}
                        max={100}
                        defaultValue={panel.level}
                        id={`range-${panel.id}`}
                        disabled={isBusy}
                        onPointerDown={startInteraction}
                        onMouseDown={startInteraction}
                        onTouchStart={startInteraction}
                        onPointerUp={endInteractionDebounced}
                        onMouseUp={endInteractionDebounced}
                        onTouchEnd={endInteractionDebounced}
                        onPointerCancel={() => {
                            if (interactionTimeoutRef.current) {
                                window.clearTimeout(interactionTimeoutRef.current)
                                interactionTimeoutRef.current = null
                            }
                            setIsInteracting(false)
                        }}
                        onBlur={() => {
                            if (interactionTimeoutRef.current) {
                                window.clearTimeout(interactionTimeoutRef.current)
                                interactionTimeoutRef.current = null
                            }
                            setIsInteracting(false)
                        }}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                            const val = Number(e.currentTarget.value)
                            setLocalLevel(val)
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
                                const el = document.getElementById(`range-${panel.id}`) as HTMLInputElement | null
                                if (el) el.value = String(v)
                                setLocalLevel(v)
                                try {
                                    await onSet(panel.id, v)
                                } catch (e) {
                                    setLocalLevel(panel.level)
                                }
                            }}
                        >
                            {v}
                        </button>
                    ))}
                </div>

                <button
                    className="panel-tile-apply-btn"
                    disabled={isBusy || readSliderValue() === panel.level}
                    onClick={async () => {
                        const val = readSliderValue()
                        try {
                            await onSet(panel.id, val)
                        } catch (e) {
                            setLocalLevel(panel.level)
                        }
                    }}
                >
                    {isBusy ? '...' : readSliderValue() === panel.level ? '✓' : 'Apply'}
                </button>
            </div>
        </div>
    )
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

