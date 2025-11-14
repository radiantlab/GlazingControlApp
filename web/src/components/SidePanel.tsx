import React, { useState } from "react";
import type { Panel, Group } from "../api";
import { useToast } from "../utils/toast";

type RoutineStep = {
    target_type: "panel" | "group";
    target_id: string;
    level: number;
    delay_after_ms: number;
};

type Routine = {
    id: string;
    name: string;
    steps: RoutineStep[];
};

type Props = {
    isOpen: boolean;
    onClose: () => void;
    panels: Panel[];
    groups: Group[];
    onGroupCreate: (name: string, memberIds: string[]) => Promise<void>;
    onGroupUpdate?: (groupId: string, name: string, memberIds: string[]) => Promise<void>;
    onGroupDelete?: (groupId: string) => Promise<void>;
    onRoutineCreate?: (routine: Omit<Routine, "id">) => Promise<void>;
};

export default function SidePanel({
    isOpen,
    onClose,
    panels,
    groups,
    onGroupCreate,
    onGroupUpdate,
    onGroupDelete,
    onRoutineCreate
}: Props) {
    const [activeTab, setActiveTab] = useState<"groups" | "routines">("groups");
    const { showToast } = useToast();

    // group creation state
    const [newGroupName, setNewGroupName] = useState("");
    const [selectedPanelIds, setSelectedPanelIds] = useState<Set<string>>(new Set());
    const [isCreatingGroup, setIsCreatingGroup] = useState(false);

    // group edit state
    const [editingGroupId, setEditingGroupId] = useState<string | null>(null);
    const [editGroupName, setEditGroupName] = useState("");
    const [editMemberIds, setEditMemberIds] = useState<Set<string>>(new Set());
    const [isSavingGroup, setIsSavingGroup] = useState(false);

    // routine creation state
    const [newRoutineName, setNewRoutineName] = useState("");
    const [routineSteps, setRoutineSteps] = useState<RoutineStep[]>([]);
    const [isCreatingRoutine, setIsCreatingRoutine] = useState(false);

    // helpers  group creation

    const handlePanelToggle = (panelId: string) => {
        setSelectedPanelIds(prev => {
            const next = new Set(prev);
            if (next.has(panelId)) next.delete(panelId);
            else next.add(panelId);
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
            setNewGroupName("");
            setSelectedPanelIds(new Set());
        } catch {
            // AppHMI shows error toast
        } finally {
            setIsCreatingGroup(false);
        }
    };

    // helpers  group edit

    const startEditingGroup = (group: Group) => {
        setEditingGroupId(group.id);
        setEditGroupName(group.name);
        // Group type from api should expose member_ids  adjust if your shape differs
        setEditMemberIds(new Set(group.member_ids));
    };

    const handleEditPanelToggle = (panelId: string) => {
        setEditMemberIds(prev => {
            const next = new Set(prev);
            if (next.has(panelId)) next.delete(panelId);
            else next.add(panelId);
            return next;
        });
    };

    const handleSaveGroupChanges = async () => {
        if (!editingGroupId || !editGroupName.trim() || !onGroupUpdate) {
            showToast("Group update not wired", "error");
            return;
        }

        setIsSavingGroup(true);
        try {
            await onGroupUpdate(
                editingGroupId,
                editGroupName.trim(),
                Array.from(editMemberIds)
            );

            // success toast is already handled in AppHMI
            // exit edit mode
            setEditingGroupId(null);
            setEditGroupName("");
            setEditMemberIds(new Set());
        } catch {
            // toast already shown in AppHMI
        } finally {
            setIsSavingGroup(false);
        }
    };


    const handleDeleteGroup = async (groupId?: string) => {
        const targetId = groupId ?? editingGroupId;
        if (!targetId || !onGroupDelete) {
            showToast("Group delete not wired", "error");
            return;
        }

        try {
            await onGroupDelete(targetId);
            if (editingGroupId === targetId) {
                setEditingGroupId(null);
                setEditGroupName("");
                setEditMemberIds(new Set());
            }
        } catch {
            // error toast already from AppHMI
        }
    };

    const cancelEditing = () => {
        setEditingGroupId(null);
        setEditGroupName("");
        setEditMemberIds(new Set());
    };

    // helpers  routines

    const handleAddRoutineStep = () => {
        setRoutineSteps(prev => [
            ...prev,
            {
                target_type: "panel",
                target_id: "",
                level: 50,
                delay_after_ms: 1000
            }
        ]);
    };

    const handleUpdateRoutineStep = (index: number, updates: Partial<RoutineStep>) => {
        setRoutineSteps(prev =>
            prev.map((step, i) => (i === index ? { ...step, ...updates } : step))
        );
    };

    const handleRemoveRoutineStep = (index: number) => {
        setRoutineSteps(prev => prev.filter((_, i) => i !== index));
    };

    const handleCreateRoutine = async () => {
        if (!newRoutineName.trim() || routineSteps.length === 0) {
            showToast("Please provide a name and add at least one step", "warning");
            return;
        }

        if (routineSteps.some(s => !s.target_id)) {
            showToast("All routine steps must have a target selected", "warning");
            return;
        }

        if (!onRoutineCreate) {
            showToast("Routine creation not yet implemented in API", "info");
            return;
        }

        setIsCreatingRoutine(true);
        try {
            await onRoutineCreate({
                name: newRoutineName.trim(),
                steps: routineSteps
            });
            setNewRoutineName("");
            setRoutineSteps([]);
            showToast("Routine created successfully", "success");
        } catch (e) {
            showToast(`Error creating routine  ${String(e)}`, "error");
        } finally {
            setIsCreatingRoutine(false);
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
                                    onChange={e => setNewGroupName(e.target.value)}
                                    placeholder="e.g., West Windows"
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
                                disabled={
                                    isCreatingGroup ||
                                    !newGroupName.trim() ||
                                    selectedPanelIds.size === 0
                                }
                            >
                                {isCreatingGroup ? "Creating..." : "Create Group"}
                            </button>

                            <div className="side-panel-section-divider" />

                            <h3>Existing Groups</h3>
                            <div className="groups-list">
                                {groups.map(group => {
                                    const isEditing = editingGroupId === group.id;
                                    return (
                                        <div key={group.id} className="group-item">
                                            <div className="group-item-header">
                                                {isEditing ? (
                                                    <input
                                                        type="text"
                                                        value={editGroupName}
                                                        onChange={e => setEditGroupName(e.target.value)}
                                                        placeholder="Group name"
                                                    />
                                                ) : (
                                                    <strong>{group.name}</strong>
                                                )}
                                                <span className="group-item-id">{group.id}</span>
                                            </div>

                                            {isEditing ? (
                                                <>
                                                    <div className="form-group">
                                                        <label>Edit members</label>
                                                        <div className="panel-selector">
                                                            {panels.map(panel => (
                                                                <label key={panel.id} className="panel-checkbox">
                                                                    <input
                                                                        type="checkbox"
                                                                        checked={editMemberIds.has(panel.id)}
                                                                        onChange={() =>
                                                                            handleEditPanelToggle(panel.id)
                                                                        }
                                                                    />
                                                                    <span>{panel.name}</span>
                                                                    <span className="panel-id">
                                                                        {panel.id}
                                                                    </span>
                                                                </label>
                                                            ))}
                                                        </div>
                                                    </div>
                                                    <div style={{ display: "flex", gap: 8 }}>
                                                        <button
                                                            className="side-panel-action-btn"
                                                            onClick={handleSaveGroupChanges}
                                                            disabled={
                                                                !editingGroupId ||
                                                                !editGroupName.trim() ||
                                                                isSavingGroup
                                                            }
                                                        >
                                                            {isSavingGroup ? "Saving..." : "Save Changes"}
                                                        </button>
                                                        <button
                                                            className="side-panel-secondary-btn"
                                                            onClick={cancelEditing}
                                                        >
                                                            Cancel
                                                        </button>
                                                    </div>
                                                </>
                                            ) : (
                                                <>
                                                    <div className="group-item-members">
                                                        {group.member_ids.length} panel
                                                        {group.member_ids.length !== 1 ? "s" : ""}
                                                    </div>
                                                    <div
                                                        style={{
                                                            display: "flex",
                                                            gap: 8,
                                                            marginTop: 8
                                                        }}
                                                    >
                                                        <button
                                                            className="side-panel-secondary-btn"
                                                            onClick={() => startEditingGroup(group)}
                                                        >
                                                            Edit
                                                        </button>
                                                        <button
                                                            className="side-panel-secondary-btn"
                                                            onClick={() => handleDeleteGroup(group.id)}
                                                            disabled={isSavingGroup}
                                                        >
                                                            Delete
                                                        </button>
                                                    </div>
                                                </>
                                            )}
                                        </div>
                                    );
                                })}
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
                                    onChange={e => setNewRoutineName(e.target.value)}
                                    placeholder="e.g., Morning Setup"
                                />
                            </div>

                            <div className="form-group">
                                <label>Steps</label>
                                <div className="routine-steps">
                                    {routineSteps.length === 0 ? (
                                        <div className="routine-steps-empty">
                                            No steps yet  click Add Step to begin
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
                                                        onChange={e =>
                                                            handleUpdateRoutineStep(index, {
                                                                target_type: e.target
                                                                    .value as "panel" | "group"
                                                            })
                                                        }
                                                    >
                                                        <option value="panel">Panel</option>
                                                        <option value="group">Group</option>
                                                    </select>
                                                    <select
                                                        value={step.target_id}
                                                        onChange={e =>
                                                            handleUpdateRoutineStep(index, {
                                                                target_id: e.target.value
                                                            })
                                                        }
                                                    >
                                                        <option value="">
                                                            Select {step.target_type}...
                                                        </option>
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
                                                            ))}
                                                    </select>
                                                    <input
                                                        type="number"
                                                        min={0}
                                                        max={100}
                                                        value={step.level}
                                                        onChange={e =>
                                                            handleUpdateRoutineStep(index, {
                                                                level: Number(e.target.value)
                                                            })
                                                        }
                                                        placeholder="Level"
                                                    />
                                                    <input
                                                        type="number"
                                                        min={0}
                                                        value={step.delay_after_ms}
                                                        onChange={e =>
                                                            handleUpdateRoutineStep(index, {
                                                                delay_after_ms: Number(e.target.value)
                                                            })
                                                        }
                                                        placeholder="Delay ms"
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
                                disabled={
                                    isCreatingRoutine ||
                                    !newRoutineName.trim() ||
                                    routineSteps.length === 0
                                }
                            >
                                {isCreatingRoutine ? "Creating..." : "Create Routine"}
                            </button>

                            <div className="side-panel-section-divider" />

                            <h3>Existing Routines</h3>
                            <div className="routines-list">
                                <div className="routines-empty">
                                    No routines created yet  routines allow you to automate
                                    sequences of tint changes
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </>
    );
}
