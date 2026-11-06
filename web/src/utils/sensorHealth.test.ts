import { describe, expect, it } from "vitest";
import type { SensorInfo, SensorReadingResponse } from "../api";
import { lastSensorReadingText, sensorDisplayLabel, sensorHealthIssues } from "./sensorHealth";

const sensors: SensorInfo[] = [
    { id: "S1", kind: "t10a", label: "Head 1", config: { device_id: "D1" } },
    {
        id: "S2", kind: "t10a", label: "Head 2",
        config: { device_id: "D1", custom_label: "Window head" },
    },
    { id: "S3", kind: "t10a", label: "Other head", config: { device_id: "D2" } },
];

describe("sensorDisplayLabel", () => {
    it("prefers the custom label, then the sensor label, then the raw ID", () => {
        expect(sensorDisplayLabel(sensors[1])).toBe("Window head");
        expect(sensorDisplayLabel({ ...sensors[0], config: { custom_label: "" } })).toBe("Head 1");
        expect(sensorDisplayLabel({ ...sensors[0], label: "", config: {} })).toBe("S1");
    });
});

describe("sensorHealthIssues", () => {
    it("maps sensor IDs to display labels and preserves error order", () => {
        expect(sensorHealthIssues(["S1: disconnected", "S2: timed out"], sensors)).toEqual([
            { raw: "S1: disconnected", reason: "disconnected", sensorIds: ["S1"], label: "Head 1" },
            { raw: "S2: timed out", reason: "timed out", sensorIds: ["S2"], label: "Window head" },
        ]);
    });

    it("maps a device ID to all of its sensor heads", () => {
        expect(sensorHealthIssues(["D1: disconnected"], sensors)).toEqual([
            {
                raw: "D1: disconnected", reason: "disconnected",
                sensorIds: ["S1", "S2"], label: "Head 1, Window head",
            },
        ]);
    });

    it("prefers an exact sensor ID over a matching device ID", () => {
        const exact: SensorInfo = { id: "D1", kind: "t10a", label: "Exact sensor", config: {} };

        expect(sensorHealthIssues(["D1: disconnected"], [...sensors, exact])).toEqual([
            {
                raw: "D1: disconnected", reason: "disconnected",
                sensorIds: ["D1"], label: "Exact sensor",
            },
        ]);
    });

    it.each([{ availableSensors: sensors }, { availableSensors: [] }])(
        "falls back to the raw ID when no sensor matches",
        ({ availableSensors }) => {
            expect(sensorHealthIssues(["UNKNOWN: disconnected"], availableSensors)).toEqual([
                {
                    raw: "UNKNOWN: disconnected", reason: "disconnected",
                    sensorIds: [], label: "UNKNOWN",
                },
            ]);
        },
    );

    it("preserves an error without a colon as the full reason", () => {
        expect(sensorHealthIssues(["Sensor service unavailable"], sensors)).toEqual([
            {
                raw: "Sensor service unavailable", reason: "Sensor service unavailable",
                sensorIds: [], label: "",
            },
        ]);
    });

    it("splits only at the first separator so the reason can contain colons", () => {
        expect(sensorHealthIssues(["S1: read failed: timed out"], sensors)).toEqual([
            {
                raw: "S1: read failed: timed out", reason: "read failed: timed out",
                sensorIds: ["S1"], label: "Head 1",
            },
        ]);
    });

    it("returns no issues when there are no errors", () => {
        expect(sensorHealthIssues([], sensors)).toEqual([]);
    });
});

describe("lastSensorReadingText", () => {
    const metrics: SensorReadingResponse[] = [
        { sensor_id: "S1", metric: "lux", value: 0, ts: 900 },
        { sensor_id: "S2", metric: "lux", value: 1, ts: 950 },
        { sensor_id: "S3", metric: "lux", value: 1, ts: 1000 },
        { sensor_id: "S1", metric: "lux", value: 1, ts: Number.NaN },
    ];

    it("distinguishes unavailable metrics from a sensor with no readings", () => {
        expect(lastSensorReadingText(["S1"], metrics, 1000, false)).toBe("Last reading unavailable");
        expect(lastSensorReadingText(["UNKNOWN"], metrics, 1000, true)).toBe("No readings available");
        expect(lastSensorReadingText(["S1"], [metrics[3]], 1000, true)).toBe("No readings available");
    });

    it("uses the newest finite timestamp belonging to the requested sensors", () => {
        expect(lastSensorReadingText(["S1", "S2"], metrics, 1000, true)).toBe("Last reading 50s ago");
    });

    it.each([
        [949, "0s"],
        [1009.9, "59s"],
        [1010, "1m 0s"],
        [4549, "59m 59s"],
        [4550, "1h 0m"],
        [87349, "23h 59m"],
        [87350, "1d 0h"],
    ])("formats reading age at time %s", (nowSeconds, age) => {
        expect(lastSensorReadingText(["S2"], metrics, nowSeconds, true)).toBe(`Last reading ${age} ago`);
    });
});
