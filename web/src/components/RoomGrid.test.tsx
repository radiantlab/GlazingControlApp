import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Panel } from "../types";
import RoomGrid from "./RoomGrid";
import RoomGridCompact from "./RoomGridCompact";

const panels: Panel[] = [
    { id: "P01", name: "Facade 1", level: 10, last_change_ts: 1000 },
    { id: "P10", name: "Facade 10", level: 20, last_change_ts: 1000 },
    { id: "SK1", name: "Skylight 1", level: 30, last_change_ts: 1000 },
    { id: "SK2", name: "Skylight 2", level: 40, last_change_ts: 1000 },
];

describe("RoomGrid", () => {
    it("splits panels into the two room sections without visible room names", () => {
        render(<RoomGrid panels={panels} onSet={vi.fn()} />);

        const room1 = screen.getByLabelText("Room 1");
        const room2 = screen.getByLabelText("Room 2");

        expect(within(room1).getByText("P01")).toBeInTheDocument();
        expect(within(room1).getByText("SK1")).toBeInTheDocument();
        expect(within(room1).queryByText("P10")).not.toBeInTheDocument();
        expect(within(room2).getByText("P10")).toBeInTheDocument();
        expect(within(room2).getByText("SK2")).toBeInTheDocument();
        expect(screen.getByRole("heading", { name: "Room 1" })).toHaveClass("visually-hidden");
        expect(screen.getByRole("heading", { name: "Room 2" })).toHaveClass("visually-hidden");
    });

    it("highlights panels in the selected group", () => {
        render(<RoomGrid panels={panels} onSet={vi.fn()} highlightedPanelIds={new Set(["P10", "SK2"])} />);

        expect(screen.getByTestId("panel-tile-P10")).toHaveClass("panel-tile-selected-group");
        expect(screen.getByTestId("panel-tile-SK2")).toHaveClass("panel-tile-selected-group");
        expect(screen.getByTestId("panel-tile-P01")).not.toHaveClass("panel-tile-selected-group");
    });
});

describe("RoomGridCompact", () => {
    it("splits compact panels by room and highlights selected group members", () => {
        render(
            <RoomGridCompact
                panels={panels}
                transitioning={new Set()}
                highlightedPanelIds={new Set(["P01"])}
            />
        );

        const room1 = screen.getByLabelText("Room 1");
        const room2 = screen.getByLabelText("Room 2");

        expect(within(room1).getByText("P01")).toBeInTheDocument();
        expect(within(room2).getByText("P10")).toBeInTheDocument();
        expect(screen.getByTestId("compact-panel-P01")).toHaveClass("room-compact-panel-selected-group");
        expect(screen.getByTestId("compact-panel-P10")).not.toHaveClass("room-compact-panel-selected-group");
    });
});
