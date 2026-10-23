import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import SystemHealthDetails from "./SystemHealthDetails";

function renderDetails() {
    render(<SystemHealthDetails
        health={{ status: "degraded", environment: "development", sensor_errors: ["Sensor disconnected"] }}
        sensors={[]}
        latestMetrics={[]}
        metricsAvailable={true}
        nowSeconds={1000}
        warnings={[]}
    >
        <span>System status degraded</span>
    </SystemHealthDetails>);
    const trigger = screen.getByRole("button");
    fireEvent.click(trigger);
    return trigger;
}

describe("SystemHealthDetails", () => {
    it("opens the details and returns focus to the trigger on Escape", () => {
        const trigger = renderDetails();
        expect(screen.getByRole("region", { name: "System health details" })).toBeVisible();
        expect(screen.getByText("Sensor disconnected")).toBeVisible();

        fireEvent.keyDown(document, { key: "Escape" });
        expect(screen.queryByRole("region")).not.toBeInTheDocument();
        expect(trigger).toHaveFocus();
    });

    it("stays open for interaction inside and dismisses on an outside click", () => {
        renderDetails();
        fireEvent.pointerDown(screen.getByText("Sensor disconnected"));
        expect(screen.getByRole("region")).toBeVisible();

        fireEvent.pointerDown(document.body);
        expect(screen.queryByRole("region")).not.toBeInTheDocument();
    });
});
