import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import PanelGrid from "./PanelGrid";

const panels = [
    { id: "P01", name: "Facade 1", level: 25, last_change_ts: 1000 },
];

describe("PanelGrid", () => {
    it("applies the slider value for a panel", async () => {
        const onSet = vi.fn().mockResolvedValue(undefined);

        render(<PanelGrid panels={panels} onSet={onSet} />);

        fireEvent.change(screen.getByRole("slider"), { target: { value: "75" } });
        fireEvent.click(screen.getByRole("button", { name: "Apply" }));

        await waitFor(() => {
            expect(onSet).toHaveBeenCalledWith("P01", 75);
        });
    });

    it("updates the range from quick-select chips", async () => {
        const onSet = vi.fn().mockResolvedValue(undefined);

        render(<PanelGrid panels={panels} onSet={onSet} />);

        fireEvent.click(screen.getByText("100"));
        fireEvent.click(screen.getByRole("button", { name: "Apply" }));

        await waitFor(() => {
            expect(onSet).toHaveBeenCalledWith("P01", 100);
        });
    });

    it("shows busy state for the panel being updated", () => {
        const onSet = vi.fn().mockResolvedValue(undefined);

        render(<PanelGrid panels={panels} onSet={onSet} busyId="P01" />);

        expect(screen.getByRole("button", { name: "Setting..." })).toBeDisabled();
    });
});
