import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useSystemHealth } from "./useSystemHealth";

const health = {
    status: "degraded",
    environment: "development",
    sensor_errors: ["TEST: disconnected"],
};
const reading = { sensor_id: "TEST", metric: "lux", ts: 1000, value: 42 };

function json(body: unknown, status = 200) {
    return new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
    });
}

describe("useSystemHealth", () => {
    const fetchMock = vi.fn<typeof fetch>();

    beforeEach(() => {
        vi.useFakeTimers();
        vi.setSystemTime(1000000);
        vi.stubGlobal("fetch", fetchMock);
        fetchMock.mockImplementation(async input => {
            if (String(input) === "/health") return json(health);
            if (String(input) === "/metrics/latest") return json([reading]);
            return json([]);
        });
    });

    afterEach(() => {
        vi.useRealTimers();
        vi.unstubAllGlobals();
    });

    it.each(["/sensors", "/metrics/latest"])(
        "updates health and reading ages while %s hangs, then times out and retries",
        async stalledPath => {
            const successfulFetch = fetchMock.getMockImplementation()!;
            fetchMock.mockImplementation((input, options) => {
                if (String(input) !== stalledPath) return successfulFetch(input, options);
                return new Promise((_, reject) => {
                    options!.signal!.addEventListener("abort", () => reject(new Error("aborted")));
                });
            });
            const { result, unmount } = renderHook(() => useSystemHealth());
            let request!: Promise<void>;
            await act(async () => { request = result.current.refreshHealth(); });

            expect(result.current.health?.status).toBe("degraded");
            expect(result.current.health?.sensor_errors).toEqual(health.sensor_errors);
            await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
            expect(result.current.nowSeconds).toBe(1005);

            await act(async () => {
                await vi.advanceTimersByTimeAsync(5000);
                await request;
            });
            expect(result.current.warnings.join(" ")).toMatch(/unavailable/i);

            fetchMock.mockImplementation(successfulFetch);
            await act(async () => { await result.current.refreshHealth(); });
            expect(result.current.warnings).toEqual([]);
            expect(result.current.latestMetrics).toEqual([reading]);
            unmount();
            expect(vi.getTimerCount()).toBe(0);
        },
    );

    it("retains readings on refresh failure and clears the warning on recovery", async () => {
        const successfulFetch = fetchMock.getMockImplementation()!;
        const { result } = renderHook(() => useSystemHealth());
        await act(async () => { await result.current.refreshHealth(); });

        fetchMock.mockImplementation((input, options) => String(input) === "/metrics/latest"
            ? Promise.resolve(json({ detail: "unavailable" }, 503))
            : successfulFetch(input, options));
        await act(async () => { await result.current.refreshHealth(); });

        expect(result.current.latestMetrics).toEqual([reading]);
        expect(result.current.metricsAvailable).toBe(true);
        expect(result.current.metricsError).toMatch(/last successful refresh/);

        fetchMock.mockImplementation(successfulFetch);
        await act(async () => { await result.current.refreshHealth(); });
        expect(result.current.metricsError).toBeNull();
    });

    it("retains known sensor errors when the health request times out", async () => {
        const successfulFetch = fetchMock.getMockImplementation()!;
        const { result } = renderHook(() => useSystemHealth());
        await act(async () => { await result.current.refreshHealth(); });
        fetchMock.mockImplementation((input, options) => {
            if (String(input) !== "/health") return successfulFetch(input, options);
            return new Promise((_, reject) => {
                options!.signal!.addEventListener("abort", () => reject(new Error("aborted")));
            });
        });
        let request!: Promise<void>;
        await act(async () => { request = result.current.refreshHealth(); });
        await act(async () => {
            await vi.advanceTimersByTimeAsync(10000);
            await request;
        });
        expect(result.current.health?.sensor_errors).toEqual(health.sensor_errors);
        expect(result.current.healthText).toBe("health unavailable");
    });
});
