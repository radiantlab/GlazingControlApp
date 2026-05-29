import type { SensorInfo, SensorReadingResponse } from "../api";

const DEFAULT_SENSOR_FRESHNESS_SECONDS = 120;
const MIN_SENSOR_FRESHNESS_SECONDS = 30;

export function sensorFreshnessWindowSeconds(sensor: SensorInfo): number {
    const intervalSeconds = Number(sensor.config?.interval_s);
    if (Number.isFinite(intervalSeconds) && intervalSeconds > 0) {
        return Math.max(MIN_SENSOR_FRESHNESS_SECONDS, intervalSeconds * 3);
    }
    return DEFAULT_SENSOR_FRESHNESS_SECONDS;
}

export function getFreshMetricsForSensor(
    sensor: SensorInfo,
    latestMetrics: SensorReadingResponse[],
    nowSeconds = Date.now() / 1000,
): SensorReadingResponse[] {
    const cutoff = nowSeconds - sensorFreshnessWindowSeconds(sensor);
    return latestMetrics.filter(metric => metric.sensor_id === sensor.id && metric.ts >= cutoff);
}

export function isSensorConnected(
    sensor: SensorInfo,
    latestMetrics: SensorReadingResponse[],
    nowSeconds = Date.now() / 1000,
): boolean {
    return getFreshMetricsForSensor(sensor, latestMetrics, nowSeconds).length > 0;
}

export function connectedSensors(
    sensors: SensorInfo[],
    latestMetrics: SensorReadingResponse[],
    nowSeconds = Date.now() / 1000,
): SensorInfo[] {
    return sensors.filter(sensor => isSensorConnected(sensor, latestMetrics, nowSeconds));
}

export function pruneVisibleSensorIds(visibleSensorIds: string[], allowedSensorIds: string[]): string[] {
    const visibleSet = new Set(visibleSensorIds);
    return allowedSensorIds.filter(id => visibleSet.has(id));
}

function t10aOrder(sensor: SensorInfo): [number, number, string] {
    const raw = `${sensor.id} ${sensor.label}`.toLowerCase();
    const parsed = raw.match(/t-?10a?\s*#?\s*(\d+).*?h(?:ead)?\s*(\d+)/i)
        || raw.match(/t10a(\d+)-h(\d+)/i);
    if (!parsed) return [999, 999, sensor.label || sensor.id];
    return [Number(parsed[1]), Number(parsed[2]), sensor.label || sensor.id];
}

function sensorKindRank(sensor: SensorInfo): number {
    if (sensor.kind === "t10a") return 0;
    if (sensor.kind === "jeti_spectraval") return 1;
    if (sensor.kind === "eko_ms90_plus") return 2;
    return 99;
}

export function sortSensorsForDisplay(sensors: SensorInfo[]): SensorInfo[] {
    return [...sensors].sort((a, b) => {
        const kindDiff = sensorKindRank(a) - sensorKindRank(b);
        if (kindDiff !== 0) return kindDiff;

        if (a.kind === "t10a" && b.kind === "t10a") {
            const [aBody, aHead, aLabel] = t10aOrder(a);
            const [bBody, bHead, bLabel] = t10aOrder(b);
            if (aBody !== bBody) return aBody - bBody;
            if (aHead !== bHead) return aHead - bHead;
            return aLabel.localeCompare(bLabel, undefined, { numeric: true });
        }

        return (a.label || a.id).localeCompare(b.label || b.id, undefined, { numeric: true });
    });
}
