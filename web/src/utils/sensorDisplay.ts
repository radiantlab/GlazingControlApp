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
