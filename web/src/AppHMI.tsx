import React, { useEffect, useState, useCallback } from "react"
import { api} from "./api";
import {Panel, Group, AuditLogEntry} from "./types"
import { mockApi } from "./mockData";
import RoomGrid from "./components/RoomGrid";
import RoomGridCompact from "./components/RoomGridCompact";
import SidePanel from "./components/SidePanel";
import ActiveControllersBar from "./components/ActiveControllersBar";
import { controlManager, type ControlSource } from "./utils/controlManager";
import { useToast } from "./utils/toast";
import LogsPanel from "./components/LogsPanel";


export default function AppHMI() {
    const [health, setHealth] = useState<string>("checking");
    const [panels, setPanels] = useState<Panel[]>([]);
    const [groups, setGroups] = useState<Group[]>([]);
    const [busy, setBusy] = useState<string | null>(null);
    const [usingMock, setUsingMock] = useState<boolean>(false);
    const [transitioning, setTransitioning] = useState<Set<string>>(new Set());
    const [sidePanelOpen, setSidePanelOpen] = useState<boolean>(false);
    const [controlState, setControlState] = useState(controlManager.getActiveControllers());
    const { showToast } = useToast();
    const [groupId, setGroupId] = useState<string>("");
    const [groupLevel, setGroupLevel] = useState<number>(50);
    const [logsPanelOpen, setLogsPanelOpen] = useState<boolean>(false);
    const [auditLogs, setAuditLogs] = useState<AuditLogEntry[]>([]);
    const [logsLoading, setLogsLoading] = useState<boolean>(false);
    const [logsError, setLogsError] = useState<string | null>(null);


    async function refresh() {
        try {
            // Try real API first
            const [p, g, h] = await Promise.all([api.panels(), api.groups(), api.health()]);
            setPanels(p);
            setGroups(g);

            // set default group only once, without stomping user choice
            if (g.length) {
                setGroupId(prev => prev || g[0].id);
            }

            setHealth(`${h.status} • ${h.mode}`);
            setUsingMock(false);
        } catch (err) {
            // Fall back to mock data if API is unavailable
            try {
                const [p, g, h] = await Promise.all([mockApi.panels(), mockApi.groups(), mockApi.health()]);
                setPanels(p);
                setGroups(g);

                if (g.length) {
                    setGroupId(prev => prev || g[0].id);
                }

                setHealth(`${h.status} • ${h.mode} (mock)`);
                setUsingMock(true);
            } catch (mockErr) {
                setHealth(`error • ${String(mockErr)}`);
                setUsingMock(false);
            }
        }
    }


    useEffect(() => {
        refresh();
        // Auto-refresh every 5 seconds to keep status current
        const interval = setInterval(refresh, 5000);
        
        // Subscribe to control state changes
        const unsubscribe = controlManager.subscribe(setControlState);
        
        return () => {
            clearInterval(interval);
            unsubscribe();
        };
    }, []);

    async function setPanel(panelId: string, level: number) {
        try {
            // Check for control conflicts
            const existingControl = controlManager.getControlSource(panelId);
            if (existingControl && existingControl.type !== 'manual') {
                const priority = existingControl.type === 'routine' ? 1 : 2;
                const manualPriority = 3; // Manual always wins
                
                // Take manual control (overrides everything)
                const source: ControlSource = { type: 'manual', panelId };
                controlManager.takeControl(source, true);
            } else {
                // Set manual control
                const source: ControlSource = { type: 'manual', panelId };
                controlManager.takeControl(source);
            }
            
            setBusy(panelId);
            if (usingMock) {
                await mockApi.setPanelLevel(panelId, level);
            } else {
                await api.setPanelLevel(panelId, level);
            }
            await refresh();
            showToast(`Panel ${panelId} set to ${level}%`, "success");
            
            // Start transition indicator - realistic time for electrochromic glass is 30-120 seconds
            // Using 5 seconds for UI demo purposes
            const TRANSITION_TIME_MS = 5000;
            setTransitioning(prev => new Set(prev).add(panelId));
            setTimeout(() => {
                setTransitioning(prev => {
                    const next = new Set(prev);
                    next.delete(panelId);
                    return next;
                });
                // Release manual control after transition completes
                controlManager.releaseControl({ type: 'manual', panelId });
            }, TRANSITION_TIME_MS);
        } catch (e) {
            // Refresh even on error to ensure UI shows actual panel state
            await refresh();
            if ((e as any)?.status === 429) {
                showToast("Panel is busy, please wait before sending another command.", "warning");
            } else {
                showToast(`Error: ${String(e)}`, "error");
            }
        } finally {
            setBusy(null);
        }
    }
    
    async function setGroup(groupId: string, level: number) {
        try {
            const group = groups.find(g => g.id === groupId);
            if (!group) {
                showToast("Group not found", "error");
                return;
            }
            
            // Take group control
            const source: ControlSource = { type: 'group', groupId, panelIds: group.member_ids };
            const result = controlManager.takeControl(source);
            
            if (result.conflicts.length > 0) {
                const confirmed = window.confirm(
                    `${result.conflicts.length} panel(s) are currently controlled. Override and proceed?`
                );
                if (!confirmed) return;
                controlManager.takeControl(source, true);
            }
            
            setBusy(groupId);
            if (usingMock) {
                await mockApi.setGroupLevel(groupId, level);
            } else {
                await api.setGroupLevel(groupId, level);
            }
            await refresh();
            showToast(`Group "${group.name}" set to ${level}%`, "success");
            
            // Release after transition (simplified - would need to track per panel)
            setTimeout(() => {
                controlManager.releaseControl(source);
            }, 5000);
        } catch (e) {
            showToast(`Error: ${String(e)}`, "error");
        } finally {
            setBusy(null);
        }
    }

    async function updateGroup(groupId: string, name: string, memberIds: string[]) {
        try {
            if (usingMock) {
                // simple mock behavior  update in mockApi if you want
                await mockApi.createGroup(name, memberIds);
            } else {
                await api.updateGroup(groupId, name, memberIds);
            }
            await refresh();
            showToast(`Group "${name}" updated`, "success");
        } catch (e) {
            const msg = `Failed to update group: ${String(e)}`;
            showToast(msg, "error");
            throw new Error(msg);
        }
    }

    async function deleteGroup(groupId: string) {
        const group = groups.find(g => g.id === groupId);
        const label = group ? `${group.name} (${group.id})` : groupId;
        const confirmed = window.confirm(`Delete group ${label}? This cannot be undone`);
        if (!confirmed) return;

        try {
            if (usingMock) {
                // remove from mockGroups and mockPanelState manually if you want
                await api.deleteGroup(groupId); // or make a mockApi.deleteGroup
            } else {
                await api.deleteGroup(groupId);
            }
            await refresh();
            showToast(`Group ${label} deleted`, "success");
        } catch (e) {
            const msg = `Failed to delete group: ${String(e)}`;
            showToast(msg, "error");
            throw new Error(msg);
        }
    }


    async function createGroup(name: string, memberIds: string[]) {
        try {
            if (usingMock) {
                await mockApi.createGroup(name, memberIds);
            } else {
                await api.createGroup(name, memberIds);
            }
            await refresh();
            showToast(`Group "${name}" created successfully`, "success");
        } catch (e) {
            const errorMsg = `Failed to create group: ${String(e)}`;
            showToast(errorMsg, "error");
            throw new Error(errorMsg);
        }
    }

    async function clearAll() {
        const confirmed = window.confirm(
            "Clear all panels to 0%? Some panels may not clear immediately if they're in dwell time."
        );
        if (!confirmed) return;

        setBusy("clear-all");
        const successful: string[] = [];
        const failed: Array<{ id: string; reason: string }> = [];

        // Try to set each panel to 0
        for (const panel of panels) {
            try {
                // Take manual control
                const source: ControlSource = { type: 'manual', panelId: panel.id };
                controlManager.takeControl(source, true); // Force override any existing control

                if (usingMock) {
                    await mockApi.setPanelLevel(panel.id, 0);
                } else {
                    await api.setPanelLevel(panel.id, 0);
                }
                successful.push(panel.id);

                // Start transition indicator
                setTransitioning(prev => new Set(prev).add(panel.id));
                setTimeout(() => {
                    setTransitioning(prev => {
                        const next = new Set(prev);
                        next.delete(panel.id);
                        return next;
                    });
                    controlManager.releaseControl(source);
                }, 5000);
            } catch (e) {
                const errorStr = String(e);
                // Check if it's a dwell time error (429)
                if (errorStr.includes('429') || errorStr.includes('dwell')) {
                    failed.push({ id: panel.id, reason: 'dwell time' });
                } else {
                    failed.push({ id: panel.id, reason: errorStr });
                }
            }
        }

        await refresh();

        // Show summary toast
        if (successful.length === panels.length) {
            showToast(`All ${panels.length} panels cleared to 0%`, "success");
        } else if (successful.length > 0) {
            const failedIds = failed.map(f => f.id).join(', ');
            showToast(
                `${successful.length} panel(s) cleared. ${failed.length} panel(s) skipped (dwell time): ${failedIds}`,
                "warning"
            );
        } else {
            showToast(`No panels could be cleared. All are in dwell time.`, "warning");
        }

        setBusy(null);
    }

    async function loadAuditLogs() {
        if (usingMock) {
            setAuditLogs([]);
            setLogsError("Logs are not available in mock mode");
            return;
        }

        try {
            setLogsLoading(true);
            setLogsError(null);
            const rows = await api.auditLogs(500);
            setAuditLogs(rows);
        } catch (e) {
            setLogsError(`Failed to load logs ${String(e)}`);
        } finally {
            setLogsLoading(false);
        }
    }


    return (
        <>
            <ActiveControllersBar
                controlState={controlState}
                onCancelRoutine={(id) => {
                    // Find and cancel routine
                    const routine = Array.from(controlState.activeRoutines.entries()).find(([k]) => k === id);
                    if (routine) {
                        controlManager.releaseControl({ type: 'routine', routineId: id, routineName: routine[1].name, panelIds: routine[1].panelIds });
                    }
                }}
                onCancelGroup={(id) => {
                    const group = groups.find(g => g.id === id);
                    if (group) {
                        controlManager.releaseControl({ type: 'group', groupId: id, panelIds: group.member_ids });
                    }
                }}
            />
            <header className="hmi-header">
                <div className="hmi-header-inner">
                    <div className="hmi-brand">
                        <div className="hmi-logo"></div>
                        <div className="hmi-brand-text">
                            <h1>Glazing Control System</h1>
                            <p>Electrochromic Panel Management</p>
                        </div>
                    </div>
                    <div className="hmi-status">
                        <div className="hmi-status-item">
                            <span className="hmi-status-label">System</span>
                            <span className={`hmi-status-value ${health.includes('ok') ? 'status-ok' : 'status-error'}`}>
                                {health.includes('ok') ? '●' : '○'}
                            </span>
                            <span className="hmi-status-text">{health}</span>
                            {usingMock && (
                                <span className="hmi-status-badge" style={{ marginLeft: '8px', fontSize: '11px', color: '#f59e0b' }}>
                                    MOCK MODE
                                </span>
                            )}
                        </div>

                        <div className="hmi-status-item">
                            <span className="hmi-status-label">Panels</span>
                            <span className="hmi-status-value">{panels.length}</span>
                        </div>

                        <button
                            className="hmi-clear-all-btn"
                            onClick={clearAll}
                            disabled={busy === "clear-all" || panels.length === 0}
                            title="Clear all panels to 0%"
                        >
                            {busy === "clear-all" ? "Clearing..." : "Clear All"}
                        </button>


                        <button
                            className="hmi-manage-btn"
                            onClick={async () => {
                                setLogsPanelOpen(true);
                                setSidePanelOpen(false);
                                await loadAuditLogs();
                            }}
                            title="View system logs"
                        >
                            Logs
                        </button>

                        <button
                            className="hmi-manage-btn"
                            onClick={() => setSidePanelOpen(true)}
                            title="Manage Groups & Routines"
                        >
                            Manage
                        </button>
                    </div>
                </div>
            </header>

            <main className={`hmi-main ${sidePanelOpen ? 'with-side-panel' : ''}`}>
                {/* group control card, same visual treatment as a room section */}
                <div className="room-section group-card">
                    <div className="room-header">
                        <h2 className="room-title">Group control</h2>
                        <div className="room-stats">
                            <span>{groups.length} groups</span>
                        </div>
                    </div>

                    <div className="room-panels-grid" style={{ padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                        <label htmlFor="hmi-group-select" className="hmi-status-label" style={{ minWidth: 56 }}>Group</label>

                        <select
                            id="hmi-group-select"
                            value={groupId}
                            onChange={e => setGroupId(e.target.value)}
                            style={{ padding: '6px 10px' }}
                        >
                            <option value="">Select a group</option>
                            {groups.map(g => (
                                <option key={g.id} value={g.id}>{g.name}</option>
                            ))}
                        </select>

                        <label htmlFor="hmi-group-level" className="hmi-status-label" style={{ marginLeft: 8 }}>Level</label>
                        <input
                            id="hmi-group-level"
                            type="number"
                            min={0}
                            max={100}
                            value={groupLevel}
                            onChange={e => setGroupLevel(Math.max(0, Math.min(100, Number(e.target.value))))}
                            style={{ width: 80, padding: '6px 8px' }}
                        />

                        <button
                            className="hmi-manage-btn"
                            onClick={() => groupId && setGroup(groupId, groupLevel)}
                            disabled={!groupId || busy === groupId}
                            title="Set selected group level"
                        >
                            {busy === groupId ? 'Setting…' : 'Set Group'}
                        </button>

                        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginLeft: 'auto' }}>
                            {[0, 25, 50, 75, 100].map(v => (
                                <button
                                    key={v}
                                    className="hmi-manage-btn"
                                    onClick={() => {
                                        setGroupLevel(v)
                                        if (groupId) setGroup(groupId, v)
                                    }}
                                    disabled={!groupId || busy === groupId}
                                    title={`Set ${v}%`}
                                >
                                    {v}
                                </button>
                            ))}
                        </div>
                    </div>
                </div>

                {/* room grids */}
                {sidePanelOpen ? (
                    <RoomGridCompact panels={panels} transitioning={transitioning} panelControls={controlState.panelControls} />
                ) : (
                    <RoomGrid
                        panels={panels}
                        onSet={setPanel}
                        busyId={busy}
                        transitioning={transitioning}
                        panelControls={controlState.panelControls}
                    />
                )}
            </main>


            <SidePanel
                isOpen={sidePanelOpen}
                onClose={() => setSidePanelOpen(false)}
                panels={panels}
                groups={groups}
                onGroupCreate={createGroup}
                onGroupUpdate={updateGroup}
                onGroupDelete={deleteGroup}
            />

            <LogsPanel
                isOpen={logsPanelOpen}
                onClose={() => setLogsPanelOpen(false)}
                auditLogs={auditLogs}
                loading={logsLoading}
                error={logsError}
                onRefresh={loadAuditLogs}
                isMock={usingMock}
            />

        </>
    );
}

