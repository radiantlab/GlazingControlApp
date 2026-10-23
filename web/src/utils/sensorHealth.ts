import type { SensorInfo, SensorReadingResponse } from "../api";

export type SensorHealthIssue = {
    raw: string;
    reason: string;
    sensorIds: string[];
    label: string;
};

export function sensorDisplayLabel(sensor: SensorInfo): string {
    return sensor.config?.custom_label || sensor.label || sensor.id;
}

export function sensorHealthIssues(errors: string[], sensors: SensorInfo[]): SensorHealthIssue[] {
    return errors.map(raw => {
        const separator = raw.indexOf(": ");
        const id = separator < 0 ? "" : raw.slice(0, separator);
        const exact = sensors.filter(sensor => sensor.id === id);
        const matches = exact.length > 0
            ? exact
            : sensors.filter(sensor => sensor.config?.device_id === id);
        return {
            raw,
            reason: separator < 0 ? raw : raw.slice(separator + 2),
            sensorIds: matches.map(sensor => sensor.id),
            label: matches.length > 0 ? matches.map(sensorDisplayLabel).join(", ") : id,
        };
    });
}

export function lastSensorReadingText(
    sensorIds: string[],
    metrics: SensorReadingResponse[],
    nowSeconds: number,
    metricsAvailable: boolean,
): string {
    if (!metricsAvailable) return "Last reading unavailable";
    const timestamps = metrics
        .filter(metric => sensorIds.includes(metric.sensor_id) && Number.isFinite(metric.ts))
        .map(metric => metric.ts);
    if (timestamps.length === 0) return "No readings available";
    const seconds = Math.max(0, Math.floor(nowSeconds - Math.max(...timestamps)));
    if (seconds < 60) return `Last reading ${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `Last reading ${minutes}m ${seconds % 60}s ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `Last reading ${hours}h ${minutes % 60}m ago`;
    return `Last reading ${Math.floor(hours / 24)}d ${hours % 24}h ago`;
}
