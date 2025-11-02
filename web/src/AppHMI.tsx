import React, { useEffect, useState } from "react";
import { api, type Panel, type Group } from "./api";
import { mockApi } from "./mockData";
import RoomGrid from "./components/RoomGrid";
import RoomGridCompact from "./components/RoomGridCompact";
import SidePanel from "./components/SidePanel";
import ActiveControllersBar from "./components/ActiveControllersBar";
import { controlManager, type ControlSource } from "./utils/controlManager";
import { useToast } from "./utils/toast";

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

    async function refresh() {
        try {
            // Try real API first
            const [p, g, h] = await Promise.all([api.panels(), api.groups(), api.health()]);
            setPanels(p);
            setGroups(g);
            setHealth(`${h.status} • ${h.mode}`);
            setUsingMock(false);
        } catch (err) {
            // Fall back to mock data if API is unavailable
            try {
                const [p, g, h] = await Promise.all([mockApi.panels(), mockApi.groups(), mockApi.health()]);
                setPanels(p);
                setGroups(g);
                setHealth(`${h.status} • ${h.mode} (mock)`);
                setUsingMock(true);
            } catch (mockErr) {
                setHealth(`error • ${String(err)}`);
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
            showToast(`Error: ${String(e)}`, "error");
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
            />
        </>
    );
}

