import React, { useState } from "react";
import type { Panel, Group } from "../api";
import { useToast } from "../utils/toast";

type Routine = {
    id: string;
    name: string;
    steps: RoutineStep[];
};

type RoutineStep = {
    target_type: "panel" | "group";
    target_id: string;
    level: number;
    delay_after_ms: number;
};

type Props = {
    isOpen: boolean;
    onClose: () => void;
    panels: Panel[];
    groups: Group[];
    onGroupCreate: (name: string, memberIds: string[]) => Promise<void>;
    onRoutineCreate?: (routine: Omit<Routine, "id">) => Promise<void>;
};

export default function SidePanel({ isOpen, onClose, panels, groups, onGroupCreate, onRoutineCreate }: Props) {
    const [activeTab, setActiveTab] = useState<"groups" | "routines">("groups");
    const { showToast } = useToast();
    
    // Group creation state
    const [newGroupName, setNewGroupName] = useState("");
    const [selectedPanelIds, setSelectedPanelIds] = useState<Set<string>>(new Set());
    const [isCreatingGroup, setIsCreatingGroup] = useState(false);
    
    // Routine creation state
    const [newRoutineName, setNewRoutineName] = useState("");
    const [routineSteps, setRoutineSteps] = useState<RoutineStep[]>([]);
    const [isCreatingRoutine, setIsCreatingRoutine] = useState(false);

    const handlePanelToggle = (panelId: string) => {
        setSelectedPanelIds(prev => {
            const next = new Set(prev);
            if (next.has(panelId)) {
                next.delete(panelId);
            } else {
                next.add(panelId);
            }
            return next;
        });
    };

    const handleCreateGroup = async () => {
        if (!newGroupName.trim() || selectedPanelIds.size === 0) {
            showToast("Please provide a name and select at least one panel", "warning");
            return;
        }
        
        setIsCreatingGroup(true);
        try {
            await onGroupCreate(newGroupName.trim(), Array.from(selectedPanelIds));
            // Reset form
            setNewGroupName("");
            setSelectedPanelIds(new Set());
            // Success toast is handled in AppHMI
        } catch (e) {
            // Error toast is handled in AppHMI
        } finally {
            setIsCreatingGroup(false);
        }
    };

    const handleAddRoutineStep = () => {
        setRoutineSteps([...routineSteps, { target_type: "panel", target_id: "", level: 50, delay_after_ms: 1000 }]);
    };

    const handleUpdateRoutineStep = (index: number, updates: Partial<RoutineStep>) => {
        setRoutineSteps(steps => steps.map((step, i) => i === index ? { ...step, ...updates } : step));
    };

    const handleRemoveRoutineStep = (index: number) => {
        setRoutineSteps(steps => steps.filter((_, i) => i !== index));
    };

    const handleCreateRoutine = async () => {
        if (!newRoutineName.trim() || routineSteps.length === 0) {
            showToast("Please provide a name and add at least one step", "warning");
            return;
        }
        
        // Validate all steps have target_id
        if (routineSteps.some(s => !s.target_id)) {
            showToast("All routine steps must have a target selected", "warning");
            return;
        }
        
        if (onRoutineCreate) {
            setIsCreatingRoutine(true);
            try {
                await onRoutineCreate({
                    name: newRoutineName.trim(),
                    steps: routineSteps
                });
                // Reset form
                setNewRoutineName("");
                setRoutineSteps([]);
                showToast("Routine created successfully!", "success");
            } catch (e) {
                showToast(`Error creating routine: ${String(e)}`, "error");
            } finally {
                setIsCreatingRoutine(false);
            }
        } else {
            showToast("Routine creation not yet implemented in API", "info");
        }
    };

    if (!isOpen) return null;

    return (
        <>
            <div className="side-panel-overlay" onClick={onClose} />
            <div className="side-panel">
                <div className="side-panel-header">
                    <h2>Manage</h2>
                    <button className="side-panel-close" onClick={onClose} aria-label="Close panel">
                        ✕
                    </button>
                </div>

                <div className="side-panel-tabs">
                    <button
                        className={`side-panel-tab ${activeTab === "groups" ? "active" : ""}`}
                        onClick={() => setActiveTab("groups")}
                    >
                        Groups
                    </button>
                    <button
                        className={`side-panel-tab ${activeTab === "routines" ? "active" : ""}`}
                        onClick={() => setActiveTab("routines")}
                    >
                        Routines
                    </button>
                </div>

                <div className="side-panel-content">
                    {activeTab === "groups" && (
                        <div className="side-panel-section">
                            <h3>Create New Group</h3>
                            <div className="form-group">
                                <label>Group Name</label>
                                <input
                                    type="text"
                                    value={newGroupName}
                                    onChange={(e) => setNewGroupName(e.target.value)}
                                    placeholder="e.g., 'West Windows'"
                                />
                            </div>

                            <div className="form-group">
                                <label>Select Panels ({selectedPanelIds.size} selected)</label>
                                <div className="panel-selector">
                                    {panels.map(panel => (
                                        <label key={panel.id} className="panel-checkbox">
                                            <input
                                                type="checkbox"
                                                checked={selectedPanelIds.has(panel.id)}
                                                onChange={() => handlePanelToggle(panel.id)}
                                            />
                                            <span>{panel.name}</span>
                                            <span className="panel-id">{panel.id}</span>
                                        </label>
                                    ))}
                                </div>
                            </div>

                            <button
                                className="side-panel-action-btn"
                                onClick={handleCreateGroup}
                                disabled={isCreatingGroup || !newGroupName.trim() || selectedPanelIds.size === 0}
                            >
                                {isCreatingGroup ? "Creating..." : "Create Group"}
                            </button>

                            <div className="side-panel-section-divider"></div>

                            <h3>Existing Groups</h3>
                            <div className="groups-list">
                                {groups.map(group => (
                                    <div key={group.id} className="group-item">
                                        <div className="group-item-header">
                                            <strong>{group.name}</strong>
                                            <span className="group-item-id">{group.id}</span>
                                        </div>
                                        <div className="group-item-members">
                                            {group.member_ids.length} panel{group.member_ids.length !== 1 ? 's' : ''}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {activeTab === "routines" && (
                        <div className="side-panel-section">
                            <h3>Create New Routine</h3>
                            <div className="form-group">
                                <label>Routine Name</label>
                                <input
                                    type="text"
                                    value={newRoutineName}
                                    onChange={(e) => setNewRoutineName(e.target.value)}
                                    placeholder="e.g., 'Morning Setup'"
                                />
                            </div>

                            <div className="form-group">
                                <label>Steps</label>
                                <div className="routine-steps">
                                    {routineSteps.length === 0 ? (
                                        <div className="routine-steps-empty">
                                            No steps yet. Click "Add Step" to begin.
                                        </div>
                                    ) : (
                                        routineSteps.map((step, index) => (
                                            <div key={index} className="routine-step">
                                                <div className="routine-step-header">
                                                    <span>Step {index + 1}</span>
                                                    <button
                                                        className="routine-step-remove"
                                                        onClick={() => handleRemoveRoutineStep(index)}
                                                    >
                                                        Remove
                                                    </button>
                                                </div>
                                                <div className="routine-step-fields">
                                                    <select
                                                        value={step.target_type}
                                                        onChange={(e) => handleUpdateRoutineStep(index, {
                                                            target_type: e.target.value as "panel" | "group"
                                                        })}
                                                    >
                                                        <option value="panel">Panel</option>
                                                        <option value="group">Group</option>
                                                    </select>
                                                    <select
                                                        value={step.target_id}
                                                        onChange={(e) => handleUpdateRoutineStep(index, {
                                                            target_id: e.target.value
                                                        })}
                                                    >
                                                        <option value="">Select {step.target_type}...</option>
                                                        {step.target_type === "panel"
                                                            ? panels.map(p => (
                                                                <option key={p.id} value={p.id}>
                                                                    {p.name} ({p.id})
                                                                </option>
                                                            ))
                                                            : groups.map(g => (
                                                                <option key={g.id} value={g.id}>
                                                                    {g.name} ({g.id})
                                                                </option>
                                                            ))
                                                        }
                                                    </select>
                                                    <input
                                                        type="number"
                                                        min="0"
                                                        max="100"
                                                        value={step.level}
                                                        onChange={(e) => handleUpdateRoutineStep(index, {
                                                            level: Number(e.target.value)
                                                        })}
                                                        placeholder="Level"
                                                    />
                                                    <input
                                                        type="number"
                                                        min="0"
                                                        value={step.delay_after_ms}
                                                        onChange={(e) => handleUpdateRoutineStep(index, {
                                                            delay_after_ms: Number(e.target.value)
                                                        })}
                                                        placeholder="Delay (ms)"
                                                    />
                                                </div>
                                            </div>
                                        ))
                                    )}
                                </div>
                                <button
                                    className="side-panel-secondary-btn"
                                    onClick={handleAddRoutineStep}
                                >
                                    + Add Step
                                </button>
                            </div>

                            <button
                                className="side-panel-action-btn"
                                onClick={handleCreateRoutine}
                                disabled={isCreatingRoutine || !newRoutineName.trim() || routineSteps.length === 0}
                            >
                                {isCreatingRoutine ? "Creating..." : "Create Routine"}
                            </button>

                            <div className="side-panel-section-divider"></div>

                            <h3>Existing Routines</h3>
                            <div className="routines-list">
                                <div className="routines-empty">
                                    No routines created yet. Routines allow you to automate sequences of tint changes.
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </>
    );
}


