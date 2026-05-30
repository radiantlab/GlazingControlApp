import type { Panel } from "../types";

export type RoomPanels = {
    room1: Panel[];
    room2: Panel[];
};

export function isSkylightPanel(panel: Panel): boolean {
    return panel.id.startsWith("SK") || panel.name.toUpperCase().includes("SK");
}

function panelSort(a: Panel, b: Panel): number {
    const aIsSkylight = isSkylightPanel(a);
    const bIsSkylight = isSkylightPanel(b);
    if (aIsSkylight && !bIsSkylight) return -1;
    if (!aIsSkylight && bIsSkylight) return 1;
    return a.id.localeCompare(b.id, undefined, { numeric: true });
}

export function organizePanelsByRoom(panels: Panel[]): RoomPanels {
    const room1: Panel[] = [];
    const room2: Panel[] = [];

    panels.forEach(panel => {
        if (panel.id === "SK1") {
            room1.push(panel);
            return;
        }

        if (panel.id === "SK2") {
            room2.push(panel);
            return;
        }

        if (panel.id.startsWith("P")) {
            const panelNum = Number.parseInt(panel.id.replace("P", ""), 10);
            if (panelNum >= 1 && panelNum <= 9) {
                room1.push(panel);
                return;
            }
            if (panelNum >= 10 && panelNum <= 18) {
                room2.push(panel);
                return;
            }
        }

        room2.push(panel);
    });

    return {
        room1: room1.sort(panelSort),
        room2: room2.sort(panelSort),
    };
}
