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

    it("sends group layout metadata in group create requests", async () => {
        fetchMock.mockResolvedValue(
            jsonResponse({ id: "G-3", name: "West", member_ids: ["P01"], layout: { columns: 2, items: [] } }),
        );

        await api.createGroup("West", ["P01"], {
            columns: 2,
            items: [{ panel_id: "P01", row: 1, column: 2 }],
        });

        const [path, options] = fetchMock.mock.calls[0];
        expect(path).toBe("/groups");
        expect(options).toMatchObject({ method: "POST" });
        expect(JSON.parse(String(options?.body))).toEqual({
            name: "West",
            member_ids: ["P01"],
            layout: {
                columns: 2,
                items: [{ panel_id: "P01", row: 1, column: 2 }],
            },
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
});
