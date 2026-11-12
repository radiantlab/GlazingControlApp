import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import AppHMI from "./AppHMI";
import { api } from "./api";
import { controlManager } from "./utils/controlManager";
import { ToastProvider } from "./utils/toast";

vi.mock("./components/LiveGraph", () => ({ default: () => null }));

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
