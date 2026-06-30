import type { Panel } from "../types";

export type RoomPanels = {
    room1: Panel[];
    room2: Panel[];
};

type RoomId = "room1" | "room2";
type PanelLocation = {
    room: RoomId;
    kind: "skylight" | "driver" | "sim";
    position: number;
};

const DRIVER_GRID_ORDER = [3, 6, 9, 2, 5, 8, 1, 4, 7];

export function isSkylightPanel(panel: Panel): boolean {
    return panel.id.toUpperCase().startsWith("SK") || panel.name.toUpperCase().includes("SK");
}

function panelSearchText(panel: Panel): string {
    return `${panel.id} ${panel.name}`.toUpperCase();
}

function parsePanelLocation(panel: Panel): PanelLocation | null {
    const id = panel.id.toUpperCase();
    const text = panelSearchText(panel);

    if (id === "SK1") return { room: "room1", kind: "skylight", position: 0 };
    if (id === "SK2") return { room: "room2", kind: "skylight", position: 0 };

    const panelMatch = /^P(\d+)$/.exec(id);
    if (panelMatch) {
        const panelNum = Number.parseInt(panelMatch[1], 10);
        if (panelNum >= 1 && panelNum <= 9) {
            return { room: "room1", kind: "sim", position: panelNum };
        }
        if (panelNum >= 10 && panelNum <= 18) {
            return { room: "room2", kind: "sim", position: panelNum - 9 };
        }
    }

    const skylightMatch = /\bSK(?:YLIGHT)?\s*[-.]?\s*1\s*[.-]\s*(1|2)\b/.exec(text);
    if (skylightMatch?.[1] === "1") {
        return { room: "room1", kind: "skylight", position: 0 };
    }
    if (skylightMatch?.[1] === "2") {
        return { room: "room2", kind: "skylight", position: 0 };
    }

    const drMatch = /\bDR\s*[-.]?\s*(1|2)\s*[.-]\s*(\d+)\b/.exec(text);
    if (drMatch) {
        const room = drMatch[1] === "1" ? "room1" : "room2";
        const driverNum = Number.parseInt(drMatch[2], 10);
        const gridPosition = DRIVER_GRID_ORDER.indexOf(driverNum);
        return {
            room,
            kind: "driver",
            position: gridPosition === -1 ? driverNum : gridPosition + 1,
        };
    }

    if (/\bROOM\s*1\b/.test(text)) return { room: "room1", kind: "driver", position: 99 };
    if (/\bROOM\s*2\b/.test(text)) return { room: "room2", kind: "driver", position: 99 };

    return null;
}

function fallbackSort(a: Panel, b: Panel): number {
    const byName = a.name.localeCompare(b.name, undefined, { numeric: true });
    if (byName !== 0) return byName;
    return a.id.localeCompare(b.id, undefined, { numeric: true });
}

function panelSort(a: Panel, b: Panel): number {
    const aLocation = parsePanelLocation(a);
    const bLocation = parsePanelLocation(b);

    if (aLocation && bLocation) {
        const kindRank = { skylight: 0, driver: 1, sim: 1 };
        const byKind = kindRank[aLocation.kind] - kindRank[bLocation.kind];
        if (byKind !== 0) return byKind;

        const byPosition = aLocation.position - bLocation.position;
        if (byPosition !== 0) return byPosition;
    } else {
        const aIsSkylight = isSkylightPanel(a);
        const bIsSkylight = isSkylightPanel(b);
        if (aIsSkylight && !bIsSkylight) return -1;
        if (!aIsSkylight && bIsSkylight) return 1;
    }

    return fallbackSort(a, b);
}

export function organizePanelsByRoom(panels: Panel[]): RoomPanels {
    const room1: Panel[] = [];
    const room2: Panel[] = [];
    const unknown: Panel[] = [];

    panels.forEach(panel => {
        const location = parsePanelLocation(panel);
        if (location?.room === "room1") {
            room1.push(panel);
            return;
        }
        if (location?.room === "room2") {
            room2.push(panel);
            return;
        }

        unknown.push(panel);
    });

    unknown.sort(fallbackSort).forEach(panel => {
        if (room1.length <= room2.length) {
            room1.push(panel);
        } else {
            room2.push(panel);
        }
    });

    return {
        room1: room1.sort(panelSort),
        room2: room2.sort(panelSort),
    };
}
