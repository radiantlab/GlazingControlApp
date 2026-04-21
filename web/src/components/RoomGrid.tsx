import type { Panel } from "../types";
import type { ControlSource } from "../utils/controlManager";
import { sortPanelsByNumber } from "../utils/panelSort";

import PanelTile from "./PanelTile";

type Props = {
    panels: Panel[];
    onSet: (panelId: string, level: number) => Promise<void>;
    busyId?: string | null;
    transitioning?: Set<string>;
    panelControls?: Map<string, ControlSource>;
};

export default function RoomGrid({
    panels,
    onSet,
    busyId,
    transitioning = new Set(),
    panelControls = new Map(),
}: Props) {
    const sortedPanels = sortPanelsByNumber(panels);

    return (
        <div className="room-grid-container">
            <div className="room-section">
                <div className="room-header">
                    <h2 className="room-title">Windows</h2>
                    <div className="room-stats">
                        <span>{sortedPanels.length} windows</span>
                    </div>
                </div>
                <div className="room-panels-grid">
                    {sortedPanels.map(panel => (
                        <PanelTile
                            key={panel.id}
                            panel={panel}
                            onSet={onSet}
                            busyId={busyId}
                            isTransitioning={transitioning.has(panel.id)}
                            controlSource={panelControls.get(panel.id)}
                            className={
                                panel.name.toUpperCase().includes("SK") || panel.id.startsWith("SK")
                                    ? "panel-tile-skylight-featured"
                                    : undefined
                            }
                        />
                    ))}
                </div>
            </div>
        </div>
    );
}
