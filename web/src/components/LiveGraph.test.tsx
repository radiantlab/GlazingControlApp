import type { ReactNode } from "react";
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, type SensorReadingResponse } from "../api";
import LiveGraph from "./LiveGraph";

// Observe the data and time scale without relying on JSDOM layout measurements.
vi.mock("recharts", () => ({
    ResponsiveContainer: ({ children }: { children: ReactNode }) => <>{children}</>,
    AreaChart: ({ data, children }: { data: SensorReadingResponse[]; children: ReactNode }) => (
        <div>
            <output data-testid="chart-data">{JSON.stringify(data)}</output>
            {children}
        </div>
    ),
    XAxis: ({ type, domain }: { type: string; domain: number[] }) => (
        <output data-testid="time-axis">{JSON.stringify({ type, domain })}</output>
    ),
    Area: () => null,
    CartesianGrid: () => null,
    Tooltip: () => null,
    YAxis: () => null,
}));

function reading(ts: number, value = ts): SensorReadingResponse {
    return { sensor_id: "S1", metric: "lux", value, ts };
}

function deferred() {
    let resolve!: (readings: SensorReadingResponse[]) => void;
    const promise = new Promise<SensorReadingResponse[]>((done) => {
        resolve = done;
    });
    return { promise, resolve };
}

describe("LiveGraph history and live requests", () => {
    beforeEach(() => {
        vi.useFakeTimers();
        vi.setSystemTime(new Date("2026-01-02T12:00:00Z"));
    });
    afterEach(() => {
        cleanup();
        vi.clearAllTimers();
        vi.useRealTimers();
    });

    it("shows loading, requests Unix seconds, sorts data and uses an elapsed-time axis", async () => {
        const pending = deferred();
        const getHistory = vi.spyOn(api, "getMetricHistory").mockReturnValue(pending.promise);
        render(<LiveGraph sensorId="S1" metric="lux" range={{ startTs: 100, endTs: 4000 }} />);
        expect(screen.getByRole("status")).toHaveTextContent("Loading graph");
        expect(getHistory).toHaveBeenCalledWith("S1", "lux", 100, 4000);
        await act(async () => pending.resolve([reading(3700), reading(100), reading(160)]));
        expect(JSON.parse(screen.getByTestId("chart-data").textContent || "[]")).toEqual([
            reading(100),
            reading(160),
            reading(3700),
        ]);
        expect(JSON.parse(screen.getByTestId("time-axis").textContent || "{}")).toEqual({
            type: "number",
            domain: [100, 4000],
        });
        await act(async () => {
            await vi.advanceTimersByTimeAsync(6000);
        });
        expect(getHistory).toHaveBeenCalledOnce();
    });

    it("distinguishes failures from empty results and retries when the same range is reapplied", async () => {
        let view!: ReturnType<typeof render>;
        const getHistory = vi
            .spyOn(api, "getMetricHistory")
            .mockRejectedValueOnce(new Error("503 unavailable"))
            .mockResolvedValue([]);
        await act(async () => {
            view = render(
                <LiveGraph sensorId="S1" metric="lux" range={{ startTs: 0, endTs: 300 }} />,
            );
        });
        expect(screen.getByRole("alert")).toHaveTextContent("Unable to load graph data");
        expect(screen.queryByText("No data available")).not.toBeInTheDocument();
        await act(async () => {
            view.rerender(
                <LiveGraph sensorId="S1" metric="lux" range={{ startTs: 0, endTs: 300 }} />,
            );
        });
        expect(getHistory).toHaveBeenCalledTimes(2);
        expect(screen.getByRole("status")).toHaveTextContent("No data available");
    });

    it("ignores late live responses after switching to history and resumes polling on return", async () => {
        const oldLive = deferred();
        const getHistory = vi
            .spyOn(api, "getMetricHistory")
            .mockReturnValueOnce(oldLive.promise)
            .mockResolvedValue([reading(200)]);
        const { rerender, unmount } = render(<LiveGraph sensorId="S1" metric="lux" />);
        await act(async () => {
            rerender(<LiveGraph sensorId="S1" metric="lux" range={{ startTs: 100, endTs: 300 }} />);
        });
        await act(async () => oldLive.resolve([reading(999)]));
        expect(screen.getByTestId("chart-data")).toHaveTextContent('"ts":200');
        expect(screen.getByTestId("chart-data")).not.toHaveTextContent('"ts":999');
        await act(async () => {
            await vi.advanceTimersByTimeAsync(6000);
        });
        expect(getHistory).toHaveBeenCalledTimes(2);
        await act(async () => {
            rerender(<LiveGraph sensorId="S1" metric="lux" />);
        });
        const now = Date.now() / 1000;
        expect(getHistory).toHaveBeenLastCalledWith("S1", "lux", now - 3600, now);
        await act(async () => {
            await vi.advanceTimersByTimeAsync(2000);
        });
        expect(getHistory).toHaveBeenCalledTimes(4);
        unmount();
        await act(async () => {
            await vi.advanceTimersByTimeAsync(4000);
        });
        expect(getHistory).toHaveBeenCalledTimes(4);
    });

    it("reloads for start, metric and sensor changes without showing superseded responses", async () => {
        const old = deferred();
        const getHistory = vi
            .spyOn(api, "getMetricHistory")
            .mockReturnValueOnce(old.promise)
            .mockResolvedValue([]);
        const { rerender } = render(
            <LiveGraph sensorId="S1" metric="lux" range={{ startTs: 100, endTs: 300 }} />,
        );
        await act(async () => {
            rerender(<LiveGraph sensorId="S1" metric="lux" range={{ startTs: 150, endTs: 300 }} />);
        });
        expect(getHistory).toHaveBeenLastCalledWith("S1", "lux", 150, 300);
        await act(async () => {
            rerender(
                <LiveGraph sensorId="S2" metric="cri_ra" range={{ startTs: 150, endTs: 300 }} />,
            );
        });
        expect(getHistory).toHaveBeenLastCalledWith("S2", "cri_ra", 150, 300);
        await act(async () => old.resolve([reading(200)]));
        expect(screen.getByRole("status")).toHaveTextContent("No data available");
    });

    it("keeps main's offline preceding-hour window and resumes when the endpoint clears", async () => {
        const getHistory = vi.spyOn(api, "getMetricHistory").mockResolvedValue([]);
        const { rerender } = render(<LiveGraph sensorId="S1" metric="lux" endTs={3600} />);
        await act(async () => {
            await vi.advanceTimersByTimeAsync(4000);
        });
        expect(getHistory).toHaveBeenCalledExactlyOnceWith("S1", "lux", 0, 3600);
        await act(async () => {
            rerender(<LiveGraph sensorId="S1" metric="lux" />);
        });
        await act(async () => {
            await vi.advanceTimersByTimeAsync(2000);
        });
        expect(getHistory).toHaveBeenCalledTimes(3);
    });

    it("does not overlap live polls while a request is pending", async () => {
        const pending = deferred();
        const getHistory = vi
            .spyOn(api, "getMetricHistory")
            .mockReturnValueOnce(pending.promise)
            .mockResolvedValue([]);
        render(<LiveGraph sensorId="S1" metric="lux" />);
        await act(async () => {
            await vi.advanceTimersByTimeAsync(8000);
        });
        expect(getHistory).toHaveBeenCalledOnce();
        await act(async () => pending.resolve([]));
        await act(async () => {
            await vi.advanceTimersByTimeAsync(2000);
        });
        expect(getHistory).toHaveBeenCalledTimes(2);
    });
});
