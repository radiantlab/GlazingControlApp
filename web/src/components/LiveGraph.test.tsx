import { render, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { api } from "../api";
import LiveGraph from "./LiveGraph";

describe("LiveGraph", () => {
    it("requests the selected range when startTs changes", async () => {
        const getHistory = vi.spyOn(api, "getMetricHistory").mockResolvedValue([]);
        const { rerender } = render(
            <LiveGraph sensorId="S1" metric="lux" startTs={120} endTs={300} />,
        );

        await waitFor(() => {
            expect(getHistory).toHaveBeenCalledWith("S1", "lux", 120, 300);
        });

        rerender(<LiveGraph sensorId="S1" metric="lux" startTs={180} endTs={300} />);

        await waitFor(() => {
            expect(getHistory).toHaveBeenCalledWith("S1", "lux", 180, 300);
        });
    });

    it("keeps the preceding-hour default when startTs is absent", async () => {
        const getHistory = vi.spyOn(api, "getMetricHistory").mockResolvedValue([]);
        render(<LiveGraph sensorId="S1" metric="lux" endTs={3600} />);

        await waitFor(() => {
            expect(getHistory).toHaveBeenCalledWith("S1", "lux", 0, 3600);
        });
    });
});
