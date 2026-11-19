import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import HistoricalTimePicker from "./HistoricalTimePicker";

function fillRange(start: string, end: string) {
    fireEvent.change(screen.getByLabelText("Start"), { target: { value: start } });
    fireEvent.change(screen.getByLabelText("End"), { target: { value: end } });
    fireEvent.click(screen.getByRole("button", { name: "Show History" }));
}

describe("HistoricalTimePicker", () => {
    afterEach(() => vi.unstubAllEnvs());
    it.each([
        ["", "", "Choose a valid"],
        ["2026-01-01T11:00", "", "Choose a valid"],
        ["2026-01-01T11:00", "2026-01-01T10:00", "Start must be before end"],
        ["2026-01-01T11:00", "2026-01-01T11:00", "Start must be before end"],
    ])("rejects invalid range %s to %s", (start, end, message) => {
        const onApply = vi.fn();
        render(
            <HistoricalTimePicker sensorLabel="Desk" onApply={onApply} onBackToLive={vi.fn()} />,
        );
        fillRange(start, end);
        expect(onApply).not.toHaveBeenCalled();
        expect(screen.getByRole("alert")).toHaveTextContent(message);
    });

    it("applies local times as Unix seconds and labels the browser timezone", () => {
        const onApply = vi.fn();
        render(
            <HistoricalTimePicker sensorLabel="Desk" onApply={onApply} onBackToLive={vi.fn()} />,
        );
        fillRange("2026-01-01T10:00", "2026-01-02T11:00");
        expect(onApply).toHaveBeenCalledWith({
            startTs: new Date(2026, 0, 1, 10).getTime() / 1000,
            endTs: new Date(2026, 0, 2, 11).getTime() / 1000,
        });
        expect(screen.getByText(/Browser-local time:/)).toHaveTextContent(
            Intl.DateTimeFormat().resolvedOptions().timeZone,
        );
    });

    it("restores the applied range on mount, keeps draft edits separate, and returns to live", () => {
        const range = {
            startTs: new Date(2026, 0, 1, 10).getTime() / 1000,
            endTs: new Date(2026, 0, 1, 11).getTime() / 1000,
        };
        const onApply = vi.fn();
        const onBackToLive = vi.fn();
        render(
            <HistoricalTimePicker
                sensorLabel="Desk"
                range={range}
                onApply={onApply}
                onBackToLive={onBackToLive}
            />,
        );
        expect(screen.getByLabelText("Start")).toHaveValue("2026-01-01T10:00");
        const appliedLabel = screen.getByRole("status").textContent;
        fireEvent.change(screen.getByLabelText("Start"), { target: { value: "2026-01-01T09:00" } });
        expect(screen.getByRole("status")).toHaveTextContent(appliedLabel || "");
        expect(onApply).not.toHaveBeenCalled();
        fireEvent.click(screen.getByRole("button", { name: "Back to Live" }));
        expect(onBackToLive).toHaveBeenCalledOnce();
    });

    it.each([
        ["2026-01-01T10:00", "2026-01-01T11:00", 1767290400, 1767294000],
        ["2026-07-01T10:00", "2026-07-01T11:00", 1782925200, 1782928800],
        ["2026-11-01T01:30", "2026-11-01T02:30", 1793521800, 1793529000],
    ])(
        "converts Pacific local time %s using the correct seasonal offset",
        (start, end, startTs, endTs) => {
            vi.stubEnv("TZ", "America/Los_Angeles");
            const onApply = vi.fn();
            render(
                <HistoricalTimePicker
                    sensorLabel="Desk"
                    onApply={onApply}
                    onBackToLive={vi.fn()}
                />,
            );
            fillRange(start, end);
            expect(onApply).toHaveBeenCalledWith({ startTs, endTs });
        },
    );

    it("rejects a nonexistent Pacific spring-forward time instead of shifting it", () => {
        vi.stubEnv("TZ", "America/Los_Angeles");
        const onApply = vi.fn();
        render(
            <HistoricalTimePicker sensorLabel="Desk" onApply={onApply} onBackToLive={vi.fn()} />,
        );
        fillRange("2026-03-08T02:30", "2026-03-08T04:00");
        expect(onApply).not.toHaveBeenCalled();
        expect(screen.getByRole("alert")).toHaveTextContent("exist in your local timezone");
    });
});
