import React from "react";
import type { Panel } from "../types";
import { isSkylightPanel, organizePanelsByRoom } from "../utils/panelRooms";
import type { ControlSource } from "../utils/controlManager";

type Props = {
    panels: Panel[];
    onSet: (panelId: string, level: number) => Promise<void>;
    busyId?: string | null;
    transitioning?: Set<string>;
    panelControls?: Map<string, ControlSource>;
    highlightedPanelIds?: Set<string>;
};

function formatLastUpdated(timestamp: number, currentTime?: number): string {
    if (!timestamp || timestamp === 0) {
        return "Never";
    }

    const now = currentTime || Date.now() / 1000;
    const diff = now - timestamp;

    if (diff < 5) return "Just now";
    if (diff < 60) {
        const seconds = Math.floor(diff);
        return `${seconds} second${seconds !== 1 ? "s" : ""} ago`;
    }
    if (diff < 3600) {
        const minutes = Math.floor(diff / 60);
        return `${minutes} minute${minutes !== 1 ? "s" : ""} ago`;
    }
    if (diff < 86400) {
        const hours = Math.floor(diff / 3600);
        return `${hours} hour${hours !== 1 ? "s" : ""} ago`;
    }
    const days = Math.floor(diff / 86400);
    return `${days} day${days !== 1 ? "s" : ""} ago`;
}

function PanelTile({
    panel,
    onSet,
    busyId,
    isTransitioning,
    controlSource,
    isHighlighted,
    className,
}: {
    panel: Panel;
    onSet: (id: string, level: number) => Promise<void>;
    busyId?: string | null;
    isTransitioning?: boolean;
    controlSource?: ControlSource | null;
    isHighlighted?: boolean;
    className?: string;
}) {
    const [localLevel, setLocalLevel] = React.useState(panel.level);
    const [currentTime, setCurrentTime] = React.useState(Date.now() / 1000);
    const [isInteracting, setIsInteracting] = React.useState(false);
    const interactionTimeoutRef = React.useRef<number | null>(null);
    const isSkylight = isSkylightPanel(panel);

    React.useEffect(() => {
        if (!isInteracting) {
            setLocalLevel(panel.level);
        }
    }, [panel.level, isInteracting]);

    React.useEffect(() => {
        if (busyId !== panel.id && localLevel !== panel.level && !isInteracting) {
            setLocalLevel(panel.level);
        }
    }, [busyId, panel.id, panel.level, localLevel, isInteracting]);

    React.useEffect(() => {
        const interval = setInterval(() => {
            setCurrentTime(Date.now() / 1000);
        }, 10000);
        return () => clearInterval(interval);
    }, []);

    React.useEffect(() => {
        return () => {
            if (interactionTimeoutRef.current) {
                window.clearTimeout(interactionTimeoutRef.current);
                interactionTimeoutRef.current = null;
            }
        };
    }, []);

    const getTintColor = (level: number) => {
        if (level === 0) return "#e8f3ff";
        if (level < 25) return "#9ec5ff";
        if (level < 50) return "#6ba3ff";
        if (level < 75) return "#3d7fd6";
        return "#1e4a8c";
    };

    const getTextColor = (level: number) => {
        return level < 50 ? "#1e293b" : "#ffffff";
    };

    const isBusy = busyId === panel.id;

    const getControlBadge = () => {
        if (!controlSource || controlSource.type === "manual") return null;
        switch (controlSource.type) {
            case "group":
                return { label: "Group", className: "control-badge-group", icon: "G" };
            case "routine":
                return { label: "Routine", className: "control-badge-routine", icon: "R" };
        }
    };

    const badge = getControlBadge();

    const getControlBorderClass = () => {
        if (!controlSource) return "panel-controlled-manual";
        return `panel-controlled-${controlSource.type}`;
    };

    const readSliderValue = () => {
        const el = document.getElementById(`range-${panel.id}`) as HTMLInputElement | null;
        if (!el) return panel.level;
        const v = Number(el.value);
        return Number.isNaN(v) ? panel.level : Math.max(0, Math.min(100, v));
    };

    const startInteraction = () => {
        if (interactionTimeoutRef.current) {
            window.clearTimeout(interactionTimeoutRef.current);
            interactionTimeoutRef.current = null;
        }
        setIsInteracting(true);
    };

    const endInteractionDebounced = () => {
        if (interactionTimeoutRef.current) {
            window.clearTimeout(interactionTimeoutRef.current);
        }
        interactionTimeoutRef.current = window.setTimeout(() => {
            interactionTimeoutRef.current = null;
            setIsInteracting(false);
        }, 600);
    };

    return (
        <div
            data-testid={`panel-tile-${panel.id}`}
            className={`panel-tile ${isSkylight ? "panel-tile-skylight" : ""} ${isBusy ? "panel-tile-busy" : ""} ${isTransitioning ? "panel-tile-transitioning" : ""} ${isHighlighted ? "panel-tile-selected-group" : ""} ${getControlBorderClass()} ${className || ""}`}
        >
            <div className="panel-tile-header">
                <div className="panel-tile-name">{panel.name}</div>
                <div className="panel-tile-header-right">
                    {badge && (
                        <div className={`control-badge ${badge.className}`} title={`Controlled by: ${badge.label}`}>
                            <span className="control-badge-icon">{badge.icon}</span>
                            <span className="control-badge-label">{badge.label}</span>
                        </div>
                    )}
                    <div className="panel-tile-id">{panel.id}</div>
                </div>
            </div>

            <div className="panel-tile-status">
                <div className="panel-tile-level-display" style={{ backgroundColor: getTintColor(localLevel) }}>
                    <span className="panel-tile-level-value" style={{ color: getTextColor(localLevel) }}>
                        {localLevel}%
                    </span>
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
                                window.clearTimeout(interactionTimeoutRef.current);
                                interactionTimeoutRef.current = null;
                            }
                            setIsInteracting(false);
                        }}
                        onBlur={() => {
                            if (interactionTimeoutRef.current) {
                                window.clearTimeout(interactionTimeoutRef.current);
                                interactionTimeoutRef.current = null;
                            }
                            setIsInteracting(false);
                        }}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                            setLocalLevel(Number(e.currentTarget.value));
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
                            onClick={() => {
                                const el = document.getElementById(`range-${panel.id}`) as HTMLInputElement | null;
                                if (el) el.value = String(v);
                                setLocalLevel(v);
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
                        const val = readSliderValue();
                        try {
                            await onSet(panel.id, val);
                        } catch (e) {
                            setLocalLevel(panel.level);
                        }
                    }}
                >
                    {isBusy ? "..." : readSliderValue() === panel.level ? "OK" : "Apply"}
                </button>
            </div>
        </div>
    );
}

export default function RoomGrid({
    panels,
    onSet,
    busyId,
    transitioning = new Set(),
    panelControls = new Map(),
    highlightedPanelIds = new Set(),
}: Props) {
    const { room1, room2 } = organizePanelsByRoom(panels);

    const renderPanel = (panel: Panel) => (
        <PanelTile
            key={panel.id}
            panel={panel}
            onSet={onSet}
            busyId={busyId}
            isTransitioning={transitioning.has(panel.id)}
            controlSource={panelControls.get(panel.id)}
            isHighlighted={highlightedPanelIds.has(panel.id)}
            className={isSkylightPanel(panel) ? "panel-tile-skylight-featured" : undefined}
        />
    );

    return (
        <div className="room-grid-container">
            <div className="rooms-layout">
                <section className="room-section" aria-label="Room 1">
                    <div className="room-header">
                        <h2 className="room-title">Room 1</h2>
                        <div className="room-stats">
                            <span>{room1.length} panels</span>
                        </div>
                    </div>
                    <div className="room-panels-grid">{room1.map(renderPanel)}</div>
                </section>

                <section className="room-section" aria-label="Room 2">
                    <div className="room-header">
                        <h2 className="room-title">Room 2</h2>
                        <div className="room-stats">
                            <span>{room2.length} panels</span>
                        </div>
                    </div>
                    <div className="room-panels-grid">{room2.map(renderPanel)}</div>
                </section>
            </div>
        </div>
    );
}
