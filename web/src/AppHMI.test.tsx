import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import AppHMI from "./AppHMI";
import { ToastProvider } from "./utils/toast";

vi.mock("./components/LiveGraph", () => ({ default: () => null }));

afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
});

describe("AppHMI sensor diagnostics", () => {
    it("warns beside cached readings immediately after a failed refresh and recovers", async () => {
        vi.useFakeTimers();
        let metricsFail = false;
        vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
            const path = String(input);
            const body = path === "/health"
                ? { status: "ok", environment: "development", sensor_errors: [] }
                : path === "/sensors"
                    ? [{ id: "TEST", label: "Test sensor", kind: "t10a", config: { interval_s: 60 } }]
                    : path === "/metrics/latest"
                        ? [{ sensor_id: "TEST", metric: "lux", value: 42, ts: Date.now() / 1000 }]
                        : [];
            return new Response(JSON.stringify(body), {
                status: path === "/metrics/latest" && metricsFail ? 503 : 200,
                headers: { "Content-Type": "application/json" },
            });
        }));
        await act(async () => {
            render(<MemoryRouter><ToastProvider><AppHMI /></ToastProvider></MemoryRouter>);
        });
        fireEvent.click(screen.getByRole("button", { name: "Sensors" }));
        expect(screen.getByText("Live metrics")).toBeVisible();

        metricsFail = true;
        await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
        expect(screen.getByText("Last readings")).toBeVisible();
        expect(screen.queryByText("Live metrics")).not.toBeInTheDocument();
        expect(screen.getByText(/Any displayed readings are from the last successful refresh/)).toBeVisible();

        metricsFail = false;
        await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
        expect(screen.getByText("Live metrics")).toBeVisible();
        expect(screen.queryByText(/Any displayed readings are from the last successful refresh/)).not.toBeInTheDocument();
    });
});
