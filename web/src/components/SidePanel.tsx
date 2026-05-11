import React, { useState } from "react";
import type { Panel, Group } from "../types";
import { useToast } from "../utils/toast";
import RoutineCodeEditor from "./RoutineCodeEditor";

type Props = {
    isOpen: boolean;
    mode: "groups" | "routines";
    onClose: () => void;
    panels: Panel[];
    groups: Group[];
    onGroupCreate: (name: string, memberIds: string[]) => Promise<void>;
    onGroupUpdate?: (groupId: string, name: string, memberIds: string[]) => Promise<void>;
    onGroupDelete?: (groupId: string) => Promise<void>;
    targetRoutineId?: string | null;
};

export default function SidePanel({
    isOpen,
    mode,
    onClose,
    panels,
    groups,
    onGroupCreate,
    onGroupUpdate,
    onGroupDelete,
    targetRoutineId
}: Props) {
    const sortedPanels = [...panels].sort((a, b) => a.name.localeCompare(b.name));
    const sortedGroups = [...groups].sort((a, b) => a.name.localeCompare(b.name));
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
            showToast("Please provide a name and select at least one window", "warning");
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

    const startEditingGroup = (group: Group) => {
        setEditingGroupId(group.id);
        setEditGroupName(group.name);
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

    if (!isOpen) return null;

    return (
        <>
            <div className="side-panel-overlay" onClick={onClose} />
            <div className="side-panel" onClick={(e) => e.stopPropagation()}>
                <div className="side-panel-header">
                    <h2>{mode === "groups" ? "Groups" : "Routines"}</h2>
                    <button className="side-panel-close" onClick={onClose} aria-label="Close panel">
                        ✕
                    </button>
                </div>

                <div className="side-panel-content">
                    {mode === "groups" && (
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
                                <label>Select Windows ({selectedPanelIds.size} selected)</label>
                                <div className="panel-selector">
                                    {sortedPanels.map(panel => (
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
                                {sortedGroups.map(group => {
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
                                                            {sortedPanels.map(panel => (
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
                                                        {group.member_ids.length} window
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

                    {mode === "routines" && (
                        <div className="side-panel-section" style={{ height: "100%", display: "flex", flexDirection: "column" }}>
                            <RoutineCodeEditor panels={panels} groups={groups} initialRoutineId={targetRoutineId} />
                        </div>
                    )}
                </div>
            </div>
        </>
    );
}
