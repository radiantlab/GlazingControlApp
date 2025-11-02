import React from "react";
import type { ControlState } from "../utils/controlManager";

type Props = {
    controlState: ControlState;
    onCancelRoutine?: (routineId: string) => void;
    onCancelGroup?: (groupId: string) => void;
};

export default function ActiveControllersBar({ controlState, onCancelRoutine, onCancelGroup }: Props) {
    const hasActive = controlState.activeRoutines.size > 0 || controlState.activeGroups.size > 0;

    if (!hasActive) return null;

    return (
        <div className="active-controllers-bar">
            <div className="active-controllers-header">
                <span className="active-controllers-label">Active Control:</span>
            </div>
            <div className="active-controllers-items">
                {Array.from(controlState.activeRoutines.entries()).map(([id, routine]) => (
                    <div key={`routine-${id}`} className="active-controller-item active-controller-routine">
                        <div className="active-controller-info">
                            <span className="active-controller-icon">⚙</span>
                            <span className="active-controller-name">{routine.name}</span>
                            <span className="active-controller-count">{routine.panelIds.length} panels</span>
                        </div>
                        {onCancelRoutine && (
                            <button
                                className="active-controller-cancel"
                                onClick={() => onCancelRoutine(id)}
                                title="Cancel routine"
                            >
                                Stop
                            </button>
                        )}
                    </div>
                ))}
                {Array.from(controlState.activeGroups.entries()).map(([id, group]) => (
                    <div key={`group-${id}`} className="active-controller-item active-controller-group">
                        <div className="active-controller-info">
                            <span className="active-controller-icon">▣</span>
                            <span className="active-controller-name">{group.name}</span>
                            <span className="active-controller-count">{group.panelIds.length} panels</span>
                        </div>
                        {onCancelGroup && (
                            <button
                                className="active-controller-cancel"
                                onClick={() => onCancelGroup(id)}
                                title="Release group control"
                            >
                                Release
                            </button>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
}


