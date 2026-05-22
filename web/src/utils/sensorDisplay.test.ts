import { describe, expect, it } from "vitest";
import type { SensorInfo, SensorReadingResponse } from "../api";
import {
    connectedSensors,
    getFreshMetricsForSensor,
    pruneVisibleSensorIds,
    sensorFreshnessWindowSeconds,
} from "./sensorDisplay";

const sensor = (id: string, interval_s?: number): SensorInfo => ({
    id,
    kind: "t10a",
    label: id,
    config: interval_s == null ? {} : { interval_s },
});

const reading = (sensor_id: string, metric: string, ts: number): SensorReadingResponse => ({
    sensor_id,
    metric,
    value: 1,
    ts,
});

describe("sensorDisplay", () => {
    it("uses three polling intervals with a 30 second minimum freshness window", () => {
        expect(sensorFreshnessWindowSeconds(sensor("fast", 5))).toBe(30);
        expect(sensorFreshnessWindowSeconds(sensor("slow", 60))).toBe(180);
        expect(sensorFreshnessWindowSeconds(sensor("unknown"))).toBe(120);
    });

    it("returns only sensors with recent latest metrics", () => {
        const sensors = [sensor("fresh", 10), sensor("stale", 10), sensor("default-window")];
        const metrics = [
            reading("fresh", "lux", 980),
            reading("stale", "lux", 969),
            reading("default-window", "lux", 879),
        ];

        expect(connectedSensors(sensors, metrics, 1000).map(s => s.id)).toEqual(["fresh"]);
    });

    it("filters stale metrics per sensor", () => {
        const readings = [
            reading("S1", "lux", 980),
            reading("S1", "board_temp_c", 960),
            reading("S2", "lux", 1000),
        ];

        expect(getFreshMetricsForSensor(sensor("S1", 10), readings, 1000).map(m => m.metric)).toEqual(["lux"]);
    });

    it("prunes visible sensors to the allowed connected sensor order", () => {
        expect(pruneVisibleSensorIds(["B", "A", "C"], ["A", "C"])).toEqual(["A", "C"]);
    });
});
