import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import AppHMI from "./AppHMI";
import { api } from "./api";
import { controlManager } from "./utils/controlManager";
import { ToastProvider } from "./utils/toast";

vi.mock("./components/LiveGraph", () => ({
    default: ({
        sensorId,
        metric,
        range,
        endTs,
    }: {
        sensorId: string;
        metric: string;
        range?: { startTs: number; endTs: number };
        endTs?: number;
    }) => (
        <output
            data-testid={`graph-${sensorId}`}
            data-metric={metric}
            data-start={range?.startTs}
            data-end={range?.endTs ?? endTs}
        />
    ),
}));

afterEach(() => {
    cleanup();
    controlManager.clearAll();
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.unstubAllGlobals();
});

describe("AppHMI dashboard", () => {
    const panels = [
        { id: "P01", name: "Facade 1", level: 25, last_change_ts: 1000 },
        { id: "P02", name: "Facade 2", level: 50, last_change_ts: 1001 },
    ];
    const groups = [
        { id: "G-facade", name: "Facade", member_ids: ["P01", "P02"] },
        { id: "G-skylights", name: "Skylights", member_ids: ["SK1", "SK2"] },
    ];

    beforeEach(() => {
        vi.useFakeTimers();
        vi.spyOn(api, "health").mockResolvedValue({
            status: "ok",
            environment: "development",
            control_source: "simulated",
            sensor_source: "simulated",
            sensor_acquisition: "embedded",
            sensor_status: "healthy",
            sensor_errors: [],
            halio_status: "not_applicable",
            halio_errors: [],
        });
        vi.spyOn(api, "panels").mockResolvedValue(panels);
        vi.spyOn(api, "groups").mockResolvedValue(groups);
        vi.spyOn(api, "listSensors").mockResolvedValue([]);
        vi.spyOn(api, "getLatestMetrics").mockResolvedValue([]);
        vi.spyOn(api, "setGroupLevel").mockResolvedValue({
            ok: true,
            applied_to: ["P01", "P02"],
            message: "group updated",
        });
    });

    async function renderDashboard() {
        await act(async () => {
            render(
                <MemoryRouter>
                    <ToastProvider>
                        <AppHMI />
                    </ToastProvider>
                </MemoryRouter>,
            );
        });
    }

    it("loads health, panels, and groups on mount", async () => {
        await renderDashboard();

        expect(screen.getByText("ok")).toBeVisible();
        expect(screen.getByText("development")).toBeVisible();
        expect(screen.getByText("Facade 1")).toBeVisible();
        expect(screen.getByText("Facade 2")).toBeVisible();
        expect(screen.getByLabelText("Group")).toHaveValue("G-facade");
        expect(screen.getByRole("option", { name: "Skylights" })).toBeInTheDocument();
        expect(screen.queryByText("MOCK MODE")).not.toBeInTheDocument();
    });

    it("submits a group tint request and refreshes the dashboard", async () => {
        await renderDashboard();
        vi.mocked(api.panels).mockResolvedValue(panels.map((panel) => ({ ...panel, level: 75 })));

        fireEvent.change(screen.getByLabelText("Tint Level"), { target: { value: "75" } });
        await act(async () => {
            fireEvent.click(screen.getByRole("button", { name: "Tint Group" }));
        });

        expect(api.setGroupLevel).toHaveBeenCalledWith("G-facade", 75, "group");
        expect(api.panels).toHaveBeenCalledTimes(2);
        expect(api.groups).toHaveBeenCalledTimes(2);
        expect(api.health).toHaveBeenCalledTimes(2);
        expect(within(screen.getByTestId("panel-tile-P01")).getByText("75%")).toBeVisible();
        expect(within(screen.getByTestId("panel-tile-P02")).getByText("75%")).toBeVisible();
        expect(screen.getByText('Group "Facade" set to 75%')).toBeVisible();
    });

    it("shows Halio failures beside sensor errors and clears them after recovery", async () => {
        const healthy = await api.health();
        const halioReason = "Halio: connection refused at http://halio.invalid/api/v3";
        vi.mocked(api.health).mockResolvedValue({
            ...healthy,
            status: "degraded",
            environment: "production",
            control_source: "physical",
            sensor_status: "degraded",
            sensor_errors: ["TEST: Sensor disconnected"],
            halio_status: "degraded",
            halio_errors: [halioReason],
        });
        await renderDashboard();
        fireEvent.click(screen.getByRole("button", { name: /degraded.*Details/ }));
        expect(screen.getByText(halioReason)).toBeVisible();
        expect(screen.getByText("Sensor disconnected")).toBeVisible();
        expect(screen.queryByText("No error details were provided.")).not.toBeInTheDocument();

        // Halio can recover while a sensor still keeps the popup degraded.
        vi.mocked(api.health).mockResolvedValue({
            ...healthy,
            status: "degraded",
            sensor_status: "degraded",
            sensor_errors: ["TEST: Sensor disconnected"],
            halio_status: "healthy",
            halio_errors: [],
        });
        await act(async () => {
            await vi.advanceTimersByTimeAsync(5000);
        });
        expect(screen.queryByText(halioReason)).not.toBeInTheDocument();
        expect(screen.getByText("Sensor disconnected")).toBeVisible();

        vi.mocked(api.health).mockResolvedValue(healthy);
        await act(async () => {
            await vi.advanceTimersByTimeAsync(5000);
        });
        expect(screen.getByText("ok")).toBeVisible();
        expect(
            screen.queryByRole("region", { name: "System health details" }),
        ).not.toBeInTheDocument();
    });

    it("shows a Halio-only degraded reason in the health popup", async () => {
        const healthy = await api.health();
        vi.mocked(api.health).mockResolvedValue({
            ...healthy,
            status: "degraded",
            environment: "production",
            control_source: "physical",
            halio_status: "degraded",
            halio_errors: ["Halio: request timed out at http://halio.invalid/api/v3"],
        });
        await renderDashboard();
        fireEvent.click(screen.getByRole("button", { name: /degraded.*Details/ }));
        expect(screen.getByText(/Halio: request timed out/)).toBeVisible();
        expect(screen.queryByText("No error details were provided.")).not.toBeInTheDocument();
    });

    it("shows a failed group tint request without reporting success", async () => {
        await renderDashboard();
        vi.mocked(api.setGroupLevel).mockRejectedValue(new Error("Controller unavailable"));

        await act(async () => {
            fireEvent.click(screen.getByRole("button", { name: "Tint Group" }));
        });

        expect(api.setGroupLevel).toHaveBeenCalledWith("G-facade", 50, "group");
        expect(screen.getByText(/Error:.*Controller unavailable/)).toBeVisible();
        expect(screen.queryByText('Group "Facade" set to 50%')).not.toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Tint Group" })).toBeEnabled();
    });
});

describe("AppHMI sensor diagnostics", () => {
    it("warns beside cached readings immediately after a failed refresh and recovers", async () => {
        vi.useFakeTimers();
        let metricsFail = false;
        vi.stubGlobal(
            "fetch",
            vi.fn(async (input: RequestInfo | URL) => {
                const path = String(input);
                const body =
                    path === "/health"
                        ? { status: "ok", environment: "development", sensor_errors: [] }
                        : path === "/sensors"
                          ? [
                                {
                                    id: "TEST",
                                    label: "Test sensor",
                                    kind: "t10a",
                                    config: { interval_s: 60 },
                                },
                            ]
                          : path === "/metrics/latest"
                            ? [
                                  {
                                      sensor_id: "TEST",
                                      metric: "lux",
                                      value: 42,
                                      ts: Date.now() / 1000,
                                  },
                              ]
                            : [];
                return new Response(JSON.stringify(body), {
                    status: path === "/metrics/latest" && metricsFail ? 503 : 200,
                    headers: { "Content-Type": "application/json" },
                });
            }),
        );
        await act(async () => {
            render(
                <MemoryRouter>
                    <ToastProvider>
                        <AppHMI />
                    </ToastProvider>
                </MemoryRouter>,
            );
        });
        fireEvent.click(screen.getByRole("button", { name: "Sensors" }));
        expect(screen.getByText("Live metrics")).toBeVisible();

        metricsFail = true;
        await act(async () => {
            await vi.advanceTimersByTimeAsync(5000);
        });
        expect(screen.getByText("Last readings")).toBeVisible();
        expect(screen.queryByText("Live metrics")).not.toBeInTheDocument();
        expect(
            screen.getByText(/Any displayed readings are from the last successful refresh/),
        ).toBeVisible();

        metricsFail = false;
        await act(async () => {
            await vi.advanceTimersByTimeAsync(5000);
        });
        expect(screen.getByText("Live metrics")).toBeVisible();
        expect(
            screen.queryByText(/Any displayed readings are from the last successful refresh/),
        ).not.toBeInTheDocument();
    });
});

describe("AppHMI historical sensor graphs", () => {
    const timestamp = new Date("2026-01-02T12:00:00Z").getTime() / 1000;
    beforeEach(() => {
        vi.useFakeTimers();
        vi.setSystemTime(timestamp * 1000);
        vi.spyOn(api, "health").mockResolvedValue({
            status: "ok",
            environment: "development",
            control_source: "simulated",
            sensor_source: "simulated",
            sensor_acquisition: "embedded",
            sensor_status: "healthy",
            sensor_errors: [],
            halio_status: "not_applicable",
            halio_errors: [],
        });
        vi.spyOn(api, "panels").mockResolvedValue([]);
        vi.spyOn(api, "groups").mockResolvedValue([]);
        vi.spyOn(api, "listSensors").mockResolvedValue([
            { id: "S1", label: "Desk", kind: "jeti_spectraval", config: { interval_s: 1 } },
            { id: "S2", label: "Window", kind: "t10a", config: { interval_s: 1 } },
            { id: "EMPTY", label: "No readings sensor", kind: "t10a", config: {} },
        ]);
        vi.spyOn(api, "getLatestMetrics").mockResolvedValue([
            { sensor_id: "S1", metric: "lux", value: 42, ts: timestamp },
            { sensor_id: "S1", metric: "cri_ra", value: 90, ts: timestamp },
            { sensor_id: "S2", metric: "lux", value: 10, ts: timestamp - 500 },
        ]);
    });

    async function openSensors() {
        await act(async () => {
            render(
                <MemoryRouter>
                    <ToastProvider>
                        <AppHMI />
                    </ToastProvider>
                </MemoryRouter>,
            );
        });
        fireEvent.click(screen.getByRole("button", { name: "Sensors" }));
    }

    function applyHistory(label = "Desk") {
        const form = within(
            screen.getByRole("form", { name: `Historical time range for ${label}` }),
        );
        fireEvent.change(form.getByLabelText("Start"), { target: { value: "2026-01-01T10:00" } });
        fireEvent.change(form.getByLabelText("End"), { target: { value: "2026-01-01T11:00" } });
        fireEvent.click(form.getByRole("button", { name: "Show History" }));
    }

    it("keeps ranges independent and preserves the no-reading and stale-sensor paths", async () => {
        await openSensors();
        expect(screen.queryByTestId("graph-EMPTY")).not.toBeInTheDocument();
        expect(screen.getByText("No readings sensor", { selector: "h2" })).toBeVisible();
        expect(screen.getByTestId("graph-S2")).toHaveAttribute("data-end", String(timestamp - 500));
        applyHistory();
        const start = String(new Date(2026, 0, 1, 10).getTime() / 1000);
        expect(screen.getByTestId("graph-S1")).toHaveAttribute("data-start", start);
        expect(screen.getByTestId("graph-S2")).not.toHaveAttribute("data-start");
        applyHistory("Window");
        fireEvent.click(
            within(screen.getByRole("form", { name: /for Window/ })).getByRole("button", {
                name: "Back to Live",
            }),
        );
        expect(screen.getByTestId("graph-S2")).not.toHaveAttribute("data-start");
        expect(screen.getByTestId("graph-S2")).toHaveAttribute("data-end", String(timestamp - 500));
        fireEvent.click(
            within(screen.getByRole("form", { name: /for Desk/ })).getByRole("button", {
                name: "Back to Live",
            }),
        );
        expect(screen.getByTestId("graph-S1")).not.toHaveAttribute("data-start");
        expect(screen.getByTestId("graph-S1")).not.toHaveAttribute("data-end");
    });

    it("retains historical range and fields through tab navigation and hiding a sensor", async () => {
        await openSensors();
        applyHistory();
        fireEvent.click(screen.getByRole("button", { name: "Control" }));
        fireEvent.click(screen.getByRole("button", { name: "Sensors" }));
        expect(
            within(screen.getByRole("form", { name: /for Desk/ })).getByLabelText("Start"),
        ).toHaveValue("2026-01-01T10:00");
        const start = screen.getByTestId("graph-S1").getAttribute("data-start");
        fireEvent.click(screen.getByTitle("Hide Desk"));
        expect(screen.queryByTestId("graph-S1")).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole("checkbox", { name: /Desk/ }));
        expect(screen.getByTestId("graph-S1")).toHaveAttribute("data-start", start);
        expect(
            within(screen.getByRole("form", { name: /for Desk/ })).getByLabelText("End"),
        ).toHaveValue("2026-01-01T11:00");
    });

    it("does not let fresh metrics replace the selected historical metric and keeps health updating", async () => {
        await openSensors();
        fireEvent.change(screen.getByLabelText("Graph metric"), { target: { value: "cri_ra" } });
        applyHistory();
        vi.mocked(api.getLatestMetrics).mockImplementation(async () => [
            { sensor_id: "S1", metric: "lux", value: 43, ts: Date.now() / 1000 },
            { sensor_id: "S1", metric: "cri_ra", value: 90, ts: timestamp },
        ]);
        await act(async () => {
            await vi.advanceTimersByTimeAsync(35000);
        });
        expect(screen.getByTestId("graph-S1")).toHaveAttribute("data-metric", "cri_ra");
        expect(screen.getByLabelText("Graph metric")).toHaveValue("cri_ra");
        expect(api.health).toHaveBeenCalledTimes(8);
        vi.mocked(api.getLatestMetrics).mockRejectedValue(new Error("503 unavailable"));
        await act(async () => {
            await vi.advanceTimersByTimeAsync(5000);
        });
        expect(screen.getByTestId("graph-S1")).toHaveAttribute("data-metric", "cri_ra");
        expect(
            screen.getAllByText(/Any displayed readings are from the last successful refresh/)
                .length,
        ).toBeGreaterThan(0);
        fireEvent.change(screen.getByLabelText("Graph metric"), { target: { value: "lux" } });
        expect(screen.getByTestId("graph-S1")).toHaveAttribute("data-metric", "lux");
        expect(screen.getByTestId("graph-S1")).toHaveAttribute("data-start");
    });
});
