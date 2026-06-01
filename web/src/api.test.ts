import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";

function jsonResponse(body: unknown, init?: ResponseInit): Response {
    return new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
        ...init,
    });
}

describe("api", () => {
    const fetchMock = vi.fn<typeof fetch>();

    beforeEach(() => {
        vi.stubGlobal("fetch", fetchMock);
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it("requests JSON health data", async () => {
        fetchMock.mockResolvedValue(jsonResponse({ status: "ok", mode: "sim" }));

        await expect(api.health()).resolves.toEqual({ status: "ok", mode: "sim" });
        expect(fetchMock).toHaveBeenCalledWith(
            "/health",
            expect.objectContaining({
                headers: expect.objectContaining({ "Content-Type": "application/json" }),
            }),
        );
    });

    it("sends panel commands with the expected payload", async () => {
        fetchMock.mockResolvedValue(
            jsonResponse({ ok: true, applied_to: ["P01"], message: "panel updated" }),
        );

        await api.setPanelLevel("P01", 60, "tester");

        const [path, options] = fetchMock.mock.calls[0];
        expect(path).toBe("/commands/set-level");
        expect(options).toMatchObject({ method: "POST" });
        expect(JSON.parse(String(options?.body))).toEqual({
            target_type: "panel",
            target_id: "P01",
            level: 60,
            actor: "tester",
        });
    });

    it("surfaces HTTP status codes in thrown errors", async () => {
        fetchMock.mockResolvedValue(
            new Response("dwell time not met", {
                status: 429,
                headers: { "Content-Type": "text/plain" },
            }),
        );

        await expect(api.setPanelLevel("P01", 70)).rejects.toThrow("429 dwell time not met");
    });

    it("builds sensor log query parameters in the request URL", async () => {
        fetchMock.mockResolvedValue(jsonResponse([]));

        await api.getSensorLogs(100, 20, "S1", "lux", 10, 50, "sensor_id", "asc");

        const [path] = fetchMock.mock.calls[0];
        expect(path).toBe(
            "/logs/sensors?limit=100&offset=20&sort_field=sensor_id&sort_dir=asc&sensor_id=S1&metric=lux&ts_from=10&ts_to=50",
        );
    });

    it("builds grouped sensor log query parameters", async () => {
        fetchMock.mockResolvedValue(jsonResponse([]));

        await api.getSensorLogs(
            100,
            0,
            undefined,
            undefined,
            undefined,
            undefined,
            "ts",
            "desc",
            { sensorIds: ["SPECTRAVAL-1", "SPECTRAVAL-2"], sensorKind: "jeti_spectraval" },
        );

        const [path] = fetchMock.mock.calls[0];
        expect(path).toBe(
            "/logs/sensors?limit=100&offset=0&sort_field=ts&sort_dir=desc&sensor_ids=SPECTRAVAL-1&sensor_ids=SPECTRAVAL-2&sensor_kind=jeti_spectraval",
        );
    });
});
