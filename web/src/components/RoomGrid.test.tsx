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
    it("splits panels into the two room sections with visible room names", () => {
        render(<RoomGrid panels={panels} onSet={vi.fn()} />);

        const room1 = screen.getByLabelText("Room 1");
        const room2 = screen.getByLabelText("Room 2");

        expect(within(room1).getByText("P01")).toBeInTheDocument();
        expect(within(room1).getByText("SK1")).toBeInTheDocument();
        expect(within(room1).queryByText("P10")).not.toBeInTheDocument();
        expect(within(room2).getByText("P10")).toBeInTheDocument();
        expect(within(room2).getByText("SK2")).toBeInTheDocument();
        expect(screen.getByRole("heading", { name: "Room 1" })).toHaveClass("room-title");
        expect(screen.getByRole("heading", { name: "Room 2" })).toHaveClass("room-title");
    });

    it("splits real-mode Halio panels by deployment names when ids are UUIDs", () => {
        const realPanels: Panel[] = [
            { id: "uuid-dr-1-1", name: "DR-1.1", level: 10, last_change_ts: 1000 },
            { id: "uuid-dr-2-1", name: "DR-2.1", level: 20, last_change_ts: 1000 },
            { id: "uuid-sk-1-1", name: "SK-1.1", level: 30, last_change_ts: 1000 },
            { id: "uuid-sk-1-2", name: "SK-1.2", level: 40, last_change_ts: 1000 },
        ];

        render(<RoomGrid panels={realPanels} onSet={vi.fn()} />);

        const room1 = screen.getByLabelText("Room 1");
        const room2 = screen.getByLabelText("Room 2");

        expect(within(room1).getByText("DR-1.1")).toBeInTheDocument();
        expect(within(room1).getByText("SK-1.1")).toBeInTheDocument();
        expect(within(room2).getByText("DR-2.1")).toBeInTheDocument();
        expect(within(room2).getByText("SK-1.2")).toBeInTheDocument();
    });

    it("keeps the complete DIAL driver set in its physical rooms", () => {
        const dialPanels: Panel[] = [
            "DR-1.1", "DR-1.2", "DR-1.3", "DR-1.4", "DR-1.5", "DR-1.6", "DR-1.7", "DR-1.8", "DR-1.9",
            "DR-2.1", "DR-2.2", "DR-2.3", "DR-2.4", "DR-2.5", "DR-2.6", "DR-2.7", "DR-2.8", "DR-2.9",
            "SK-1.1", "SK-1.2",
        ].map(name => ({ id: `uuid-${name}`, name, level: 0, last_change_ts: 1000 }));

        render(<RoomGrid panels={dialPanels} onSet={vi.fn()} />);

        const room1 = screen.getByLabelText("Room 1");
        const room2 = screen.getByLabelText("Room 2");

        expect(within(room1).getByText("10 panels")).toBeInTheDocument();
        expect(within(room2).getByText("10 panels")).toBeInTheDocument();
        expect(within(room1).queryByText(/^DR-2\./)).not.toBeInTheDocument();
        expect(within(room2).queryByText(/^DR-1\./)).not.toBeInTheDocument();
        expect(within(room1).getByText("SK-1.1")).toBeInTheDocument();
        expect(within(room2).getByText("SK-1.2")).toBeInTheDocument();
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
