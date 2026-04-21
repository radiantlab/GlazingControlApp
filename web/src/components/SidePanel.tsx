import React, { useRef, useState } from "react";

import type { Group, GroupLayout, Panel } from "../types";
import { normalizeGroupLayout } from "../utils/groupLayout";
import { useToast } from "../utils/toast";
import GroupLayoutEditor from "./GroupLayoutEditor";
import RoutineCodeEditor from "./RoutineCodeEditor";

type Props = {
    isOpen: boolean;
    mode: "groups" | "routines";
    onClose: () => void;
    panels: Panel[];
    groups: Group[];
    onGroupCreate: (name: string, memberIds: string[], layout: GroupLayout | null) => Promise<void>;
    onGroupUpdate?: (groupId: string, name: string, memberIds: string[], layout: GroupLayout | null) => Promise<void>;
    onGroupDelete?: (groupId: string) => Promise<void>;
    targetRoutineId?: string | null;
};

const MIN_SIDE_PANEL_WIDTH = 420;
const MAX_SIDE_PANEL_WIDTH = 900;

function togglePanelSelection(
    previous: Set<string>,
    panelId: string,
): Set<string> {
    const next = new Set(previous);
    if (next.has(panelId)) next.delete(panelId);
    else next.add(panelId);
    return next;
}

function clampSidePanelWidth(width: number): number {
    const viewportLimit = typeof window === "undefined"
        ? MAX_SIDE_PANEL_WIDTH
        : Math.max(MIN_SIDE_PANEL_WIDTH, window.innerWidth - 48);
    return Math.max(MIN_SIDE_PANEL_WIDTH, Math.min(width, MAX_SIDE_PANEL_WIDTH, viewportLimit));
}

export default function SidePanel({
    isOpen,
    mode,
    onClose,
    panels,
    groups,
    onGroupCreate,
    onGroupUpdate,
    onGroupDelete,
    targetRoutineId,
}: Props) {
    const sortedGroups = [...groups].sort((a, b) => a.name.localeCompare(b.name));
    const { showToast } = useToast();
    const [panelWidth, setPanelWidth] = useState(520);
    const resizeRef = useRef<{ startX: number; startWidth: number } | null>(null);

    const [newGroupName, setNewGroupName] = useState("");
    const [selectedPanelIds, setSelectedPanelIds] = useState<Set<string>>(new Set());
    const [newGroupLayout, setNewGroupLayout] = useState<GroupLayout | null>(null);
    const [isCreatingGroup, setIsCreatingGroup] = useState(false);

    const [editingGroupId, setEditingGroupId] = useState<string | null>(null);
    const [editGroupName, setEditGroupName] = useState("");
    const [editMemberIds, setEditMemberIds] = useState<Set<string>>(new Set());
    const [editGroupLayout, setEditGroupLayout] = useState<GroupLayout | null>(null);
    const [isSavingGroup, setIsSavingGroup] = useState(false);

    const handleCreatePanelToggle = (panelId: string) => {
        const next = togglePanelSelection(selectedPanelIds, panelId);
        setSelectedPanelIds(next);
        setNewGroupLayout(normalizeGroupLayout(Array.from(next), newGroupLayout));
    };

    const handleCreateGroup = async () => {
        if (!newGroupName.trim() || selectedPanelIds.size === 0) {
            showToast("Please provide a name and select at least one window", "warning");
            return;
        }

        setIsCreatingGroup(true);
        try {
            const memberIds = Array.from(selectedPanelIds);
            await onGroupCreate(newGroupName.trim(), memberIds, normalizeGroupLayout(memberIds, newGroupLayout));
            setNewGroupName("");
            setSelectedPanelIds(new Set());
            setNewGroupLayout(null);
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
        setEditGroupLayout(normalizeGroupLayout(group.member_ids, group.layout));
    };

    const handleEditPanelToggle = (panelId: string) => {
        const next = togglePanelSelection(editMemberIds, panelId);
        setEditMemberIds(next);
        setEditGroupLayout(normalizeGroupLayout(Array.from(next), editGroupLayout));
    };

    const handleSaveGroupChanges = async () => {
        if (!editingGroupId || !editGroupName.trim() || !onGroupUpdate) {
            showToast("Group update not wired", "error");
            return;
        }

        setIsSavingGroup(true);
        try {
            const memberIds = Array.from(editMemberIds);
            await onGroupUpdate(
                editingGroupId,
                editGroupName.trim(),
                memberIds,
                normalizeGroupLayout(memberIds, editGroupLayout),
            );
            setEditingGroupId(null);
            setEditGroupName("");
            setEditMemberIds(new Set());
            setEditGroupLayout(null);
        } catch {
            // AppHMI shows error toast
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
                setEditGroupLayout(null);
            }
        } catch {
            // AppHMI shows error toast
        }
    };

    const cancelEditing = () => {
        setEditingGroupId(null);
        setEditGroupName("");
        setEditMemberIds(new Set());
        setEditGroupLayout(null);
    };

    const startResizing = (event: React.MouseEvent<HTMLDivElement>) => {
        event.preventDefault();
        event.stopPropagation();
        resizeRef.current = { startX: event.clientX, startWidth: panelWidth };
        document.body.classList.add("side-panel-resizing");

        const handleMouseMove = (moveEvent: MouseEvent) => {
            const state = resizeRef.current;
            if (!state) return;
            setPanelWidth(clampSidePanelWidth(state.startWidth + state.startX - moveEvent.clientX));
        };

        const stopResizing = () => {
            resizeRef.current = null;
            document.body.classList.remove("side-panel-resizing");
            document.removeEventListener("mousemove", handleMouseMove);
            document.removeEventListener("mouseup", stopResizing);
        };

        document.addEventListener("mousemove", handleMouseMove);
        document.addEventListener("mouseup", stopResizing);
    };

    if (!isOpen) return null;

    return (
        <>
            <div className="side-panel-overlay" onClick={onClose} />
            <div
                className="side-panel"
                style={{ width: `min(${panelWidth}px, calc(100vw - 24px))` }}
                onClick={event => event.stopPropagation()}
            >
                <div
                    className="side-panel-resize-handle"
                    role="separator"
                    aria-orientation="vertical"
                    aria-label="Resize side panel"
                    onMouseDown={startResizing}
                />
                <div className="side-panel-header">
                    <h2>{mode === "groups" ? "Groups" : "Routines"}</h2>
                    <button className="side-panel-close" onClick={onClose} aria-label="Close panel">
                        X
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
                                    onChange={event => setNewGroupName(event.target.value)}
                                    placeholder="e.g., West Windows"
                                />
                            </div>

                            <GroupLayoutEditor
                                panels={panels}
                                selectedPanelIds={selectedPanelIds}
                                onTogglePanel={handleCreatePanelToggle}
                                layout={newGroupLayout}
                                onLayoutChange={setNewGroupLayout}
                            />

                            <button
                                className="side-panel-action-btn"
                                onClick={handleCreateGroup}
                                disabled={isCreatingGroup || !newGroupName.trim() || selectedPanelIds.size === 0}
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
                                                        onChange={event => setEditGroupName(event.target.value)}
                                                        placeholder="Group name"
                                                    />
                                                ) : (
                                                    <div className="group-item-title">
                                                        <strong>{group.name}</strong>
                                                        <span className="group-item-layout-status">
                                                            {group.layout ? "Custom 2D layout" : "Auto layout"}
                                                        </span>
                                                    </div>
                                                )}
                                                <span className="group-item-id">{group.id}</span>
                                            </div>

                                            {isEditing ? (
                                                <>
                                                    <GroupLayoutEditor
                                                        panels={panels}
                                                        selectedPanelIds={editMemberIds}
                                                        onTogglePanel={handleEditPanelToggle}
                                                        layout={editGroupLayout}
                                                        onLayoutChange={setEditGroupLayout}
                                                    />
                                                    <div className="group-item-actions">
                                                        <button
                                                            className="side-panel-action-btn"
                                                            onClick={handleSaveGroupChanges}
                                                            disabled={!editGroupName.trim() || isSavingGroup}
                                                        >
                                                            {isSavingGroup ? "Saving..." : "Save Changes"}
                                                        </button>
                                                        <button className="side-panel-secondary-btn" onClick={cancelEditing}>
                                                            Cancel
                                                        </button>
                                                    </div>
                                                </>
                                            ) : (
                                                <>
                                                    <div className="group-item-members">
                                                        {group.member_ids.length} window{group.member_ids.length !== 1 ? "s" : ""}
                                                    </div>
                                                    <div className="group-item-actions">
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
