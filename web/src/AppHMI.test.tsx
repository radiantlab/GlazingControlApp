import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import AppHMI from "./AppHMI";
import { ToastProvider } from "./utils/toast";

vi.mock("./components/LiveGraph", () => ({
    default: ({ startTs, endTs }: { startTs?: number; endTs?: number }) => (
        <div data-testid="sensor-graph" data-start-ts={startTs} data-end-ts={endTs} />
    ),
}));

afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
});

describe("AppHMI sensor diagnostics", () => {
    it("applies a historical range and returns the graph to live mode", async () => {
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
                headers: { "Content-Type": "application/json" },
            });
        }));

        await act(async () => {
            render(<MemoryRouter><ToastProvider><AppHMI /></ToastProvider></MemoryRouter>);
        });
        fireEvent.click(screen.getByRole("button", { name: "Sensors" }));

        fireEvent.change(screen.getByLabelText("Start"), {
            target: { value: "2026-01-01T10:00" },
        });
        fireEvent.change(screen.getByLabelText("End"), {
            target: { value: "2026-01-01T11:00" },
        });
        fireEvent.click(screen.getByRole("button", { name: "Show History" }));

        expect(screen.getByTestId("sensor-graph")).toHaveAttribute(
            "data-start-ts",
            String(new Date("2026-01-01T10:00").getTime() / 1000),
        );
        expect(screen.getByTestId("sensor-graph")).toHaveAttribute(
            "data-end-ts",
            String(new Date("2026-01-01T11:00").getTime() / 1000),
        );

        fireEvent.click(screen.getByRole("button", { name: "Back to Live" }));
        expect(screen.getByTestId("sensor-graph")).not.toHaveAttribute("data-start-ts");
        expect(screen.getByTestId("sensor-graph")).not.toHaveAttribute("data-end-ts");
    });

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
