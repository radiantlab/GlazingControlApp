import type { Panel } from "../types";

function panelSortKey(panel: Panel): { prefix: string; number: number; label: string } {
    const idMatch = panel.id.match(/^([A-Za-z]+)(\d+)$/);
    const nameMatch = panel.name.match(/^(.*?)(\d+)$/);
    const match = idMatch || nameMatch;
    if (!match) {
        return { prefix: panel.name.toLowerCase(), number: Number.POSITIVE_INFINITY, label: panel.name.toLowerCase() };
    }

    return {
        prefix: match[1].toLowerCase(),
        number: Number(match[2]),
        label: panel.name.toLowerCase(),
    };
}

export function sortPanelsByNumber(panels: Panel[]): Panel[] {
    return [...panels].sort((a, b) => {
        const aKey = panelSortKey(a);
        const bKey = panelSortKey(b);
        const prefixCompare = aKey.prefix.localeCompare(bKey.prefix);
        if (prefixCompare !== 0) return prefixCompare;
        if (aKey.number !== bKey.number) return aKey.number - bKey.number;
        return aKey.label.localeCompare(bKey.label);
    });
}
