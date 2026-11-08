import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type { SensorInfo, SensorReadingResponse } from "../api";
import {
    lastSensorReadingText,
    sensorDisplayLabel,
    sensorHealthIssues,
} from "../utils/sensorHealth";
import "./SystemHealthDetails.css";

type Props = {
    health: { status: string; environment: string; sensor_errors: string[] } | null;
    sensors: SensorInfo[];
    latestMetrics: SensorReadingResponse[];
    metricsAvailable: boolean;
    nowSeconds: number;
    warnings: string[];
    children: ReactNode;
};

export default function SystemHealthDetails({
    health,
    sensors,
    latestMetrics,
    metricsAvailable,
    nowSeconds,
    warnings,
    children,
}: Props) {
    const [open, setOpen] = useState(false);
    const triggerRef = useRef<HTMLButtonElement>(null);
    const panelRef = useRef<HTMLElement>(null);
    const panelId = useId();
    const interactive = health?.status === "degraded" || warnings.length > 0;

    useEffect(() => {
        if (!interactive) setOpen(false);
    }, [interactive]);

    useEffect(() => {
        if (!open) return;
        const dismiss = (event: PointerEvent) => {
            if (
                event.target instanceof Node &&
                !triggerRef.current?.contains(event.target) &&
                !panelRef.current?.contains(event.target)
            )
                setOpen(false);
        };
        const onKeyDown = (event: KeyboardEvent) => {
            if (event.key === "Escape") {
                setOpen(false);
                triggerRef.current?.focus();
            }
        };
        document.addEventListener("pointerdown", dismiss);
        document.addEventListener("keydown", onKeyDown);
        return () => {
            document.removeEventListener("pointerdown", dismiss);
            document.removeEventListener("keydown", onKeyDown);
        };
    }, [open]);

    if (!interactive) return <>{children}</>;
    const issues = sensorHealthIssues(health?.sensor_errors || [], sensors);

    return (
        <div className="system-health">
            <button
                type="button"
                className="system-health-trigger"
                ref={triggerRef}
                aria-expanded={open}
                aria-controls={open ? panelId : undefined}
                onClick={() => setOpen((previous) => !previous)}
            >
                {children}
                <span className="system-health-hint">
                    Details <span aria-hidden="true">{open ? "▴" : "▾"}</span>
                </span>
            </button>
            {open &&
                createPortal(
                    <section
                        id={panelId}
                        ref={panelRef}
                        className="system-health-panel"
                        aria-label="System health details"
                        // biome-ignore lint/a11y/noNoninteractiveTabindex: the panel scrolls, so it must take keyboard focus for keyboard users to scroll it
                        tabIndex={0}
                    >
                        <strong>System health details</strong>
                        {warnings.map((warning) => (
                            <p className="system-health-warning" key={warning}>
                                {warning}
                            </p>
                        ))}
                        {health && (
                            <p>
                                {warnings.length > 0 ? "Last reported status" : "Status"}:{" "}
                                {health.status} • {health.environment}
                            </p>
                        )}
                        {issues.length > 0 ? (
                            <ul>
                                {issues.map((issue, index) => (
                                    // biome-ignore lint/suspicious/noArrayIndexKey: rows have no stable unique id
                                    <li key={`${issue.raw}-${index}`}>
                                        {issue.label && <strong>{issue.label}: </strong>}
                                        {issue.reason}
                                        {issue.sensorIds.map((sensorId) => (
                                            <span className="system-health-age" key={sensorId}>
                                                {issue.sensorIds.length > 1 &&
                                                    // biome-ignore lint/style/noNonNullAssertion: the sensor id comes from this issue list, which is built from the loaded sensors, so the lookup always finds one
                                                    `${sensorDisplayLabel(sensors.find((sensor) => sensor.id === sensorId)!)}: `}
                                                {lastSensorReadingText(
                                                    [sensorId],
                                                    latestMetrics,
                                                    nowSeconds,
                                                    metricsAvailable,
                                                )}
                                            </span>
                                        ))}
                                    </li>
                                ))}
                            </ul>
                        ) : health?.status === "degraded" ? (
                            <p>No sensor error details were provided.</p>
                        ) : null}
                    </section>,
                    document.body,
                )}
        </div>
    );
}
