import { describe, expect, it, vi } from "vitest";
import { ControlManager } from "./controlManager";

describe("ControlManager", () => {
    it("blocks lower-priority control when a panel is already manually controlled", () => {
        const manager = new ControlManager();

        manager.takeControl({ type: "manual", panelId: "P01" });
        const result = manager.takeControl({
            type: "routine",
            routineId: "routine-1",
            routineName: "Morning",
            panelIds: ["P01"],
        });

        expect(result).toEqual({ success: false, conflicts: ["P01"] });
        expect(manager.getControlSource("P01")).toEqual({ type: "manual", panelId: "P01" });
    });

    it("supports forced takeover and cleans up active controllers on release", () => {
        const manager = new ControlManager();
        const group = { type: "group" as const, groupId: "group-1", panelIds: ["P01", "P02"] };
        const routine = {
            type: "routine" as const,
            routineId: "routine-1",
            routineName: "Morning",
            panelIds: ["P01", "P02"],
        };

        manager.takeControl(group);
        manager.takeControl(routine, true);

        expect(manager.getControlSource("P01")).toEqual(routine);
        expect(manager.getActiveControllers().activeGroups.has("group-1")).toBe(true);

        manager.releaseControl(group);
        expect(manager.getActiveControllers().activeGroups.has("group-1")).toBe(false);

        manager.releaseControl(routine);
        expect(manager.getControlSource("P01")).toBeNull();
    });

    it("notifies subscribers when state changes", () => {
        const manager = new ControlManager();
        const listener = vi.fn();
        const unsubscribe = manager.subscribe(listener);

        manager.takeControl({ type: "manual", panelId: "P01" });
        manager.clearAll();
        unsubscribe();

        expect(listener).toHaveBeenCalledTimes(2);
        expect(listener.mock.calls[0][0].panelControls.get("P01")).toEqual({
            type: "manual",
            panelId: "P01",
        });
        expect(listener.mock.calls[1][0].panelControls.size).toBe(0);
    });
});
