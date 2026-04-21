import React from "react";

import type { Panel } from "../types";
import type { ControlSource } from "../utils/controlManager";

type Props = {
    panel: Panel;
    onSet: (id: string, level: number) => Promise<void>;
    busyId?: string | null;
    isTransitioning?: boolean;
    controlSource?: ControlSource | null;
    className?: string;
};

function formatLastUpdated(timestamp: number, currentTime?: number): string {
    if (!timestamp || timestamp === 0) {
        return "Never";
    }

    const now = currentTime || (Date.now() / 1000);
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

function getTintColor(level: number) {
    if (level === 0) return "#e8f3ff";
    if (level < 25) return "#9ec5ff";
    if (level < 50) return "#6ba3ff";
    if (level < 75) return "#3d7fd6";
    return "#1e4a8c";
}

function getTextColor(level: number) {
    return level < 50 ? "#1e293b" : "#ffffff";
}

export default function PanelTile({
    panel,
    onSet,
    busyId,
    isTransitioning,
    controlSource,
    className,
}: Props) {
    const [localLevel, setLocalLevel] = React.useState(panel.level);
    const [currentTime, setCurrentTime] = React.useState(Date.now() / 1000);
    const [isInteracting, setIsInteracting] = React.useState(false);
    const interactionTimeoutRef = React.useRef<number | null>(null);
    const isSkylight = panel.name.toUpperCase().includes("SK") || panel.id.startsWith("SK");

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
        const interval = window.setInterval(() => {
            setCurrentTime(Date.now() / 1000);
        }, 10000);
        return () => window.clearInterval(interval);
    }, []);

    React.useEffect(() => () => {
        if (interactionTimeoutRef.current) {
            window.clearTimeout(interactionTimeoutRef.current);
            interactionTimeoutRef.current = null;
        }
    }, []);

    const isBusy = busyId === panel.id;

    const badge = (() => {
        if (!controlSource || controlSource.type === "manual") return null;
        switch (controlSource.type) {
            case "group":
                return { label: "Group", className: "control-badge-group", icon: "G" };
            case "routine":
                return { label: "Routine", className: "control-badge-routine", icon: "R" };
        }
    })();

    const controlBorderClass = !controlSource
        ? "panel-controlled-manual"
        : `panel-controlled-${controlSource.type}`;

    const readSliderValue = () => {
        const element = document.getElementById(`range-${panel.id}`) as HTMLInputElement | null;
        if (!element) return panel.level;
        const value = Number(element.value);
        return Number.isNaN(value) ? panel.level : Math.max(0, Math.min(100, value));
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
            className={`panel-tile ${isSkylight ? "panel-tile-skylight" : ""} ${isBusy ? "panel-tile-busy" : ""} ${isTransitioning ? "panel-tile-transitioning" : ""} ${controlBorderClass} ${className || ""}`}
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
                        onChange={(event: React.ChangeEvent<HTMLInputElement>) => {
                            setLocalLevel(Number(event.currentTarget.value));
                        }}
                        className="panel-tile-slider"
                    />
                </div>

                <div className="panel-tile-quick-controls">
                    {[0, 25, 50, 75, 100].map(value => (
                        <button
                            key={value}
                            className="panel-tile-quick-btn"
                            disabled={isBusy}
                            onClick={() => {
                                const element = document.getElementById(`range-${panel.id}`) as HTMLInputElement | null;
                                if (element) element.value = String(value);
                                setLocalLevel(value);
                            }}
                        >
                            {value}
                        </button>
                    ))}
                </div>

                <button
                    className="panel-tile-apply-btn"
                    disabled={isBusy || readSliderValue() === panel.level}
                    onClick={async () => {
                        const value = readSliderValue();
                        try {
                            await onSet(panel.id, value);
                        } catch {
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
