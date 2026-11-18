import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import HistoricalTimePicker from "./HistoricalTimePicker";

describe("HistoricalTimePicker", () => {
    it("rejects reversed times and applies a valid range in Unix seconds", () => {
        const onApply = vi.fn();
        render(
            <HistoricalTimePicker
                isHistorical={false}
                onApply={onApply}
                onBackToLive={vi.fn()}
            />,
        );

        fireEvent.change(screen.getByLabelText("Start"), {
            target: { value: "2026-01-01T11:00" },
        });
        fireEvent.change(screen.getByLabelText("End"), {
            target: { value: "2026-01-01T10:00" },
        });
        fireEvent.click(screen.getByRole("button", { name: "Show History" }));

        expect(onApply).not.toHaveBeenCalled();
        expect(screen.getByRole("alert")).toHaveTextContent("Start must be before end.");

        fireEvent.change(screen.getByLabelText("End"), {
            target: { value: "2026-01-01T12:00" },
        });
        fireEvent.click(screen.getByRole("button", { name: "Show History" }));

        expect(onApply).toHaveBeenCalledWith({
            startTs: new Date("2026-01-01T11:00").getTime() / 1000,
            endTs: new Date("2026-01-01T12:00").getTime() / 1000,
        });
    });
});
