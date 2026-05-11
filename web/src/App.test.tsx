import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { api } from "./api";

vi.mock("./api", () => ({
    api: {
        health: vi.fn(),
        panels: vi.fn(),
        groups: vi.fn(),
        setPanelLevel: vi.fn(),
        setGroupLevel: vi.fn(),
    },
}));

const mockedApi = vi.mocked(api);
const panels = [
    { id: "P01", name: "Facade 1", level: 25, last_change_ts: 1000 },
    { id: "P02", name: "Facade 2", level: 75, last_change_ts: 1001 },
];
const groups = [
    { id: "G-facade", name: "Facade", member_ids: ["P01", "P02"] },
    { id: "G-skylights", name: "Skylights", member_ids: ["SK1", "SK2"] },
];

describe("App", () => {
    beforeEach(() => {
        mockedApi.health.mockResolvedValue({ status: "ok", mode: "sim" });
        mockedApi.panels.mockResolvedValue(panels);
        mockedApi.groups.mockResolvedValue(groups);
        mockedApi.setPanelLevel.mockResolvedValue({
            ok: true,
            applied_to: ["P01"],
            message: "panel updated",
        });
        mockedApi.setGroupLevel.mockResolvedValue({
            ok: true,
            applied_to: ["P01", "P02"],
            message: "group updated",
        });
    });

    it("loads health, panels, and groups on mount", async () => {
        render(<App />);

        expect(await screen.findByText(/ok\s+mode\s+sim/i)).toBeInTheDocument();
        expect(await screen.findByText("Facade 1")).toBeInTheDocument();
        expect(screen.getByLabelText("group")).toHaveValue("G-facade");
    });

    it("submits a group tint request and refreshes the dashboard", async () => {
        render(<App />);

        await screen.findByText("Facade 1");

        fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "75" } });
        fireEvent.click(screen.getByRole("button", { name: "Tint Group" }));

        await waitFor(() => {
            expect(mockedApi.setGroupLevel).toHaveBeenCalledWith("G-facade", 75);
        });
        expect(mockedApi.panels).toHaveBeenCalledTimes(2);
        expect(mockedApi.groups).toHaveBeenCalledTimes(2);
        expect(mockedApi.health).toHaveBeenCalledTimes(2);
    });
});
