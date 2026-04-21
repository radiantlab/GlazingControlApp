import React, { useEffect, useRef, useState } from "react"
import { api } from "./api";
import { Panel, Group, GroupLayout, AuditLogEntry } from "./types"
import { mockApi } from "./mockData";
import RoomGrid from "./components/RoomGrid";
import GroupLayoutView from "./components/GroupLayoutView";
import SidePanel from "./components/SidePanel";
import ActiveControllersBar from "./components/ActiveControllersBar";
import { controlManager, type ControlSource } from "./utils/controlManager";
import { useToast } from "./utils/toast";
import LogsPanel from "./components/LogsPanel";
import LiveGraph from "./components/LiveGraph";
import { type SensorInfo, type SensorReadingResponse } from "./api";

const METRIC_LABELS: Record<string, string> = {
    lux: "Illuminance (lx)",
    cie1931_x: "CIE 1931 xy chromaticity [x]",
    cie1931_y: "CIE 1931 xy chromaticity [y]",
    s_cone_irradiance_mw_m2: "S-cone-opic irradiance (mW/m2)",
    m_cone_irradiance_mw_m2: "M-cone-opic irradiance (mW/m2)",
    l_cone_irradiance_mw_m2: "L-cone-opic irradiance (mW/m2)",
    rhodopic_irradiance_mw_m2: "Rhodopic irradiance (mW/m2)",
    melanopic_irradiance_mw_m2: "Melanopic irradiance (mW/m2)",
    s_cone_edi_lx: "S-cone-opic EDI (lx)",
    m_cone_edi_lx: "M-cone-opic EDI (lx)",
    l_cone_edi_lx: "L-cone-opic EDI (lx)",
    rhodopic_edi_lx: "Rhodopic EDI (lx)",
    melanopic_edi_lx: "Melanopic EDI (lx)",
    cct_ohno_k: "CCT (K) - Ohno, 2013",
    cct_robertson_k: "CCT (K) - Robertson, 1968",
    cri_ra: "Colour Rendering Index [Ra]",
    cfi_rf: "Colour Fidelity Index [Rf]",
    duv_ohno: "Duv - Ohno, 2013",
    duv_robertson: "Duv - Robertson, 1968",
    sample_interval_s: "Sample interval (s)",
    lux_calc: "Calculated illuminance (lx)",
    board_temp_c: "Board temperature (degC)",
    sensor_temp_c: "Sensor temperature (degC)",
    ghi_w_m2: "Global horizontal irradiance (W/m2)",
    dni_w_m2: "Direct normal irradiance (W/m2)",
    dhi_w_m2: "Diffuse horizontal irradiance (W/m2)",
    latitude_deg: "Latitude (deg)",
    longitude_deg: "Longitude (deg)",
    sun_elevation_deg: "Sun elevation (deg)",
    sun_azimuth_deg: "Sun azimuth (deg)",
    gps_timestamp_s: "GPS timestamp (s)",
    gps_satellites: "GPS satellites",
};

const SENSOR_METRIC_ORDER: Record<string, string[]> = {
    t10a: ["lux"],
    jeti_spectraval: [
        "lux",
        "cie1931_x",
        "cie1931_y",
        "s_cone_irradiance_mw_m2",
        "m_cone_irradiance_mw_m2",
        "l_cone_irradiance_mw_m2",
        "rhodopic_irradiance_mw_m2",
        "melanopic_irradiance_mw_m2",
        "s_cone_edi_lx",
        "m_cone_edi_lx",
        "l_cone_edi_lx",
        "rhodopic_edi_lx",
        "melanopic_edi_lx",
        "cct_ohno_k",
        "cct_robertson_k",
        "cri_ra",
        "cfi_rf",
        "duv_ohno",
        "duv_robertson",
        "sample_interval_s",
    ],
    eko_ms90_plus: [
        "ghi_w_m2",
        "dni_w_m2",
        "dhi_w_m2",
        "sun_elevation_deg",
        "sun_azimuth_deg",
        "board_temp_c",
        "sensor_temp_c",
        "gps_satellites",
        "latitude_deg",
        "longitude_deg",
        "gps_timestamp_s",
    ],
};

const SENSOR_GRAPH_PRIORITY: Record<string, string[]> = {
    t10a: ["lux"],
    jeti_spectraval: [
        "lux",
        "melanopic_edi_lx",
        "melanopic_irradiance_mw_m2",
        "cct_ohno_k",
        "cri_ra",
        "cfi_rf",
    ],
    eko_ms90_plus: [
        "ghi_w_m2",
        "dni_w_m2",
        "dhi_w_m2",
        "sun_elevation_deg",
        "board_temp_c",
        "sensor_temp_c",
    ],
};

const SENSOR_KIND_LABELS: Record<string, string> = {
    t10a: "T-10A",
    jeti_spectraval: "JETI",
    eko_ms90_plus: "EKO MS-90+",
};

const SENSOR_GRAPH_COLORS: Record<string, string> = {
    t10a: "#22c55e",
    jeti_spectraval: "#ebad34",
    eko_ms90_plus: "#38bdf8",
};

function orderMetrics(kind: string, metricNames: string[]): string[] {
    const order = SENSOR_METRIC_ORDER[kind] || [];
    const ordered = order.filter(metric => metricNames.includes(metric));
    const extras = metricNames
        .filter(metric => !order.includes(metric))
        .sort((a, b) => a.localeCompare(b));
    return [...ordered, ...extras];
}

function graphMetricOptions(kind: string, metricNames: string[]): string[] {
    const priority = SENSOR_GRAPH_PRIORITY[kind] || [];
    const preferred = priority.filter(metric => metricNames.includes(metric));
    const extras = metricNames.filter(metric => !preferred.includes(metric));
    return [...preferred, ...extras];
}

function sensorGraphColor(kind: string): string {
    return SENSOR_GRAPH_COLORS[kind] || "#8884d8";
}

function formatMetricValue(metric: string, value: number): string {
    if (metric === "sample_interval_s") return `${value.toFixed(2)} s`;
    if (metric === "gps_timestamp_s") return `${Math.round(value)} s`;
    if (metric === "gps_satellites") return value.toFixed(0);
    if (metric.endsWith("_w_m2")) return `${value.toFixed(2)} W/m2`;
    if (metric.endsWith("_deg")) return `${value.toFixed(2)} deg`;
    if (metric.endsWith("_temp_c") || metric.endsWith("_c")) return `${value.toFixed(2)} degC`;
    if (metric === "lux" || metric.endsWith("_edi_lx")) return `${value.toFixed(2)} lx`;
    if (metric.startsWith("cct_")) return `${value.toFixed(1)} K`;
    if (metric.startsWith("duv_")) return value.toFixed(6);
    if (metric === "cri_ra" || metric === "cfi_rf") return value.toFixed(3);
    if (metric.startsWith("cie1931_")) return value.toFixed(4);
    return value.toFixed(4);
}


export default function AppHMI() {
    const [health, setHealth] = useState<string>("checking");
    const [mainTab, setMainTab] = useState<"control" | "sensors">("control");
    const [panels, setPanels] = useState<Panel[]>([]);
    const [groups, setGroups] = useState<Group[]>([]);
    const [busy, setBusy] = useState<string | null>(null);
    const [usingMock, setUsingMock] = useState<boolean>(false);
    const [transitioning, setTransitioning] = useState<Set<string>>(new Set());
    const [sidePanelOpen, setSidePanelOpen] = useState<boolean>(false);
    const [controlState, setControlState] = useState(controlManager.getActiveControllers());
    const [sidePanelMode, setSidePanelMode] = useState<"groups" | "routines">("groups");
    const { showToast } = useToast();
    const [groupId, setGroupId] = useState<string>("");
    const [groupLevel, setGroupLevel] = useState<number>(50);
    const [controlViewMode, setControlViewMode] = useState<"flat" | "grouped">("flat");
    const [logsPanelOpen, setLogsPanelOpen] = useState<boolean>(false);
    const [auditLogs, setAuditLogs] = useState<AuditLogEntry[]>([]);
    const [logsLoading, setLogsLoading] = useState<boolean>(false);
    const [logsError, setLogsError] = useState<string | null>(null);
    const [sensors, setSensors] = useState<SensorInfo[]>([]);
    const [latestMetrics, setLatestMetrics] = useState<SensorReadingResponse[]>([]);
    const [graphMetricBySensor, setGraphMetricBySensor] = useState<Record<string, string>>({});
    const [visibleSensorIds, setVisibleSensorIds] = useState<string[]>([]);
    const sensorVisibilityUserSet = useRef(false);
    const [targetRoutineId, setTargetRoutineId] = useState<string | null>(null);


    async function refresh() {
        try {
            // Try real API first
            const [p, g, h, s, m] = await Promise.all([
                api.panels(),
                api.groups(),
                api.health(),
                api.listSensors(),
                api.getLatestMetrics(),
            ]);
            setPanels(p);
            setGroups(g);
            setSensors(s);
            setLatestMetrics(m);

            setGroupId(prev => (g.some(group => group.id === prev) ? prev : (g[0]?.id || "")));

            setHealth(`${h.status} • ${h.mode}`);
            setUsingMock(false);
        } catch (err) {
            // Fall back to mock data if API is unavailable
            try {
                const [p, g, h] = await Promise.all([mockApi.panels(), mockApi.groups(), mockApi.health()]);
                setPanels(p);
                setGroups(g);
                setSensors([]);
                setLatestMetrics([]);

                setGroupId(prev => (g.some(group => group.id === prev) ? prev : (g[0]?.id || "")));

                setHealth(`${h.status} • ${h.mode} (mock)`);
                setUsingMock(true);
            } catch (mockErr) {
                setSensors([]);
                setLatestMetrics([]);
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

    useEffect(() => {
        const sensorIds = sensors.map(sensor => sensor.id);
        if (!sensorIds.length) {
            setVisibleSensorIds([]);
            return;
        }

        if (!sensorVisibilityUserSet.current) {
            // Initial/default behavior: show all sensors.
            setVisibleSensorIds(sensorIds);
            return;
        }

        setVisibleSensorIds(prev => {
            const prevSet = new Set(prev);
            return sensorIds.filter(id => prevSet.has(id));
        });
    }, [sensors]);

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
                await api.setPanelLevel(panelId, level, "manual");
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
                await api.setGroupLevel(groupId, level, "group");
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

    async function updateGroup(groupId: string, name: string, memberIds: string[], layout: GroupLayout | null) {
        try {
            if (usingMock) {
                await mockApi.updateGroup(groupId, name, memberIds, layout);
            } else {
                await api.updateGroup(groupId, name, memberIds, layout);
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
                await mockApi.deleteGroup(groupId);
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


    async function createGroup(name: string, memberIds: string[], layout: GroupLayout | null) {
        try {
            if (usingMock) {
                await mockApi.createGroup(name, memberIds, layout);
            } else {
                await api.createGroup(name, memberIds, layout);
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

    const visibleSensors = sensors.filter(sensor => visibleSensorIds.includes(sensor.id));


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
                            onClick={() => {
                                setSidePanelMode("groups");
                                setSidePanelOpen(true);
                            }}
                            title="Manage Groups"
                        >
                            Groups
                        </button>

                        <button
                            className="hmi-manage-btn"
                            onClick={() => {
                                setSidePanelMode("routines");
                                setSidePanelOpen(true);
                            }}
                            title="Manage Routines"
                        >
                            Routines
                        </button>
                    </div>
                </div>
            </header>

            <main className="hmi-main">
                <div className="hmi-main-tabs">
                    <button
                        className={`hmi-main-tab ${mainTab === "control" ? "active" : ""}`}
                        onClick={() => setMainTab("control")}
                    >
                        Control
                    </button>
                    <button
                        className={`hmi-main-tab ${mainTab === "sensors" ? "active" : ""}`}
                        onClick={() => setMainTab("sensors")}
                    >
                        Sensors
                    </button>
                </div>

                {mainTab === "control" && (
                    <>
                        {/* group control card, same visual treatment as a room section */}
                        <div className="room-section group-card">
                            <div className="room-header">
                                <h2 className="room-title">Group control</h2>
                                <div className="room-stats">
                                    <span>{groups.length} groups</span>
                                </div>
                            </div>

                            <div className="room-panels-grid" style={{ padding: '8px 16px', display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                                <label htmlFor="hmi-group-select" className="hmi-status-label" style={{ minWidth: 56 }}>Group</label>

                                <select
                                    id="hmi-group-select"
                                    className="hmi-control-select hmi-group-select"
                                    value={groupId}
                                    onChange={e => setGroupId(e.target.value)}
                                >
                                    <option value="">Select a group</option>
                                    {groups.map(g => (
                                        <option key={g.id} value={g.id}>{g.name}</option>
                                    ))}
                                </select>

                                <label htmlFor="hmi-group-level" className="hmi-status-label" style={{ marginLeft: 8 }}>Tint Level</label>
                                <input
                                    id="hmi-group-level"
                                    type="number"
                                    min={0}
                                    max={100}
                                    value={groupLevel}
                                    onChange={e => setGroupLevel(Math.max(0, Math.min(100, Number(e.target.value))))}
                                    className="hmi-control-input hmi-group-level-input"
                                />

                                <button
                                    className="hmi-manage-btn hmi-control-action-btn"
                                    onClick={() => groupId && setGroup(groupId, groupLevel)}
                                    disabled={!groupId || busy === groupId}
                                    title="Set selected group level"
                                >
                                    {busy === groupId ? 'Setting...' : 'Tint Group'}
                                </button>


                            </div>
                        </div>

                        <div className="room-section control-view-card">
                            <div className="room-header">
                                <h2 className="room-title">Panel organization</h2>
                            </div>
                            <div className="control-view-toggle" role="tablist" aria-label="Panel organization view">
                                <button
                                    className={`control-view-toggle-btn ${controlViewMode === "flat" ? "active" : ""}`}
                                    onClick={() => setControlViewMode("flat")}
                                >
                                    List View
                                </button>
                                <button
                                    className={`control-view-toggle-btn ${controlViewMode === "grouped" ? "active" : ""}`}
                                    onClick={() => setControlViewMode("grouped")}
                                >
                                    Group View
                                </button>
                            </div>
                        </div>

                        {controlViewMode === "grouped" ? (
                            <GroupLayoutView
                                panels={panels}
                                groups={groupId ? groups.filter(group => group.id === groupId) : []}
                                onSet={setPanel}
                                busyId={busy}
                                transitioning={transitioning}
                                panelControls={controlState.panelControls}
                                emptyMessage={groupId ? "The selected group has no windows to display." : "Select a group in Group control to display its 2D layout."}
                            />
                        ) : (
                            <RoomGrid
                                panels={panels}
                                onSet={setPanel}
                                busyId={busy}
                                transitioning={transitioning}
                                panelControls={controlState.panelControls}
                            />
                        )}

                    </>
                )}

                {/* Sensor Metrics + Live Graph Section */}
                {mainTab === "sensors" && !usingMock && sensors.length > 0 && (
                    <div className="room-section" style={{ marginTop: 20 }}>
                        <div className="room-header">
                            <h2 className="room-title">Visible sensors</h2>
                            <div className="room-stats">
                                <span>{visibleSensors.length} of {sensors.length} shown</span>
                            </div>
                        </div>
                        <div className="sensor-visibility-controls">
                            <button
                                className="sensor-visibility-chip"
                                onClick={() => {
                                    sensorVisibilityUserSet.current = true;
                                    setVisibleSensorIds(sensors.map(sensor => sensor.id));
                                }}
                            >
                                Show all
                            </button>
                            <button
                                className="sensor-visibility-chip"
                                onClick={() => {
                                    sensorVisibilityUserSet.current = true;
                                    setVisibleSensorIds([]);
                                }}
                            >
                                Hide all
                            </button>
                            {sensors.map(sensor => {
                                const active = visibleSensorIds.includes(sensor.id);
                                return (
                                    <button
                                        key={`visibility-${sensor.id}`}
                                        className={`sensor-visibility-chip ${active ? "active" : ""}`}
                                        onClick={() => {
                                            sensorVisibilityUserSet.current = true;
                                            setVisibleSensorIds(prev =>
                                                prev.includes(sensor.id)
                                                    ? prev.filter(id => id !== sensor.id)
                                                    : [...prev, sensor.id]
                                            );
                                        }}
                                        title={`${sensor.label || sensor.id} (${SENSOR_KIND_LABELS[sensor.kind] || sensor.kind})`}
                                    >
                                        {sensor.label || sensor.id}
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                )}

                {mainTab === "sensors" && !usingMock && visibleSensors.map(sensor => {
                    const sensorMetrics = latestMetrics.filter(m => m.sensor_id === sensor.id);
                    const metricMap = new Map<string, number>();
                    sensorMetrics.forEach(m => metricMap.set(m.metric, m.value));
                    const metricNames = Array.from(metricMap.keys());
                    const orderedMetricNames = orderMetrics(sensor.kind, metricNames);
                    const availableGraphMetrics = graphMetricOptions(sensor.kind, metricNames);
                    const selectedGraphMetric = graphMetricBySensor[sensor.id]
                        || availableGraphMetrics[0]
                        || "";
                    const sensorKindLabel = SENSOR_KIND_LABELS[sensor.kind] || sensor.kind;
                    const graphMetricSelector = availableGraphMetrics.length > 1 ? (
                        <div className="sensor-graph-controls-inline">
                            <label className="hmi-status-label" htmlFor={`sensor-graph-metric-${sensor.id}`}>Graph metric</label>
                            <select
                                id={`sensor-graph-metric-${sensor.id}`}
                                className="sensor-graph-select"
                                value={selectedGraphMetric}
                                onChange={(e) => {
                                    const nextMetric = e.target.value;
                                    setGraphMetricBySensor(prev => ({ ...prev, [sensor.id]: nextMetric }));
                                }}
                            >
                                {availableGraphMetrics.map(metric => (
                                    <option key={`${sensor.id}-graph-${metric}`} value={metric}>
                                        {METRIC_LABELS[metric] || metric}
                                    </option>
                                ))}
                            </select>
                        </div>
                    ) : null;

                    return (
                        <div
                            key={sensor.id}
                            className={`sensor-dashboard-row ${selectedGraphMetric ? "" : "metrics-only"}`}
                        >
                            <div className="room-section sensor-metrics-panel">
                                <div className="room-header">
                                    <h2 className="room-title">{`${sensor.label || sensor.id} - Latest metrics`}</h2>
                                    <div className="room-stats">
                                        <span>{sensorKindLabel}</span>
                                        {sensor.location && <span style={{ marginLeft: 8 }}>{sensor.location}</span>}
                                        <span style={{ marginLeft: 8 }}>{orderedMetricNames.length} metrics</span>
                                    </div>
                                </div>
                                <div className="sensor-metrics-grid">
                                    {orderedMetricNames.length === 0 && (
                                        <div className="sensor-metrics-empty">
                                            Waiting for sensor data...
                                        </div>
                                    )}
                                    {orderedMetricNames.map(metric => (
                                        <React.Fragment key={`${sensor.id}-${metric}`}>
                                            <div className="sensor-metric-name">{METRIC_LABELS[metric] || metric}</div>
                                            <div className="sensor-metric-value">
                                                {formatMetricValue(metric, metricMap.get(metric) as number)}
                                            </div>
                                        </React.Fragment>
                                    ))}
                                </div>
                            </div>

                            {selectedGraphMetric && (
                                <LiveGraph
                                    sensorId={sensor.id}
                                    metric={selectedGraphMetric}
                                    label={`${sensor.label || sensor.id} - ${METRIC_LABELS[selectedGraphMetric] || selectedGraphMetric}`}
                                    color={sensorGraphColor(sensor.kind)}
                                    height={360}
                                    toolbar={graphMetricSelector}
                                    className="sensor-graph-panel"
                                />
                            )}
                        </div>
                    );
                })}

                {mainTab === "sensors" && !usingMock && sensors.length > 0 && visibleSensors.length === 0 && (
                    <div className="room-section" style={{ marginTop: 20, padding: "12px 16px", color: "#9ca3af" }}>
                        No sensors selected for display. Use the visibility controls above to choose what to show.
                    </div>
                )}

                {mainTab === "sensors" && !usingMock && sensors.length === 0 && (
                    <div className="room-section" style={{ marginTop: 20, padding: "12px 16px", color: "#9ca3af" }}>
                        No sensors are currently registered. Check `svc/data/sensors_config.json` and restart the service.
                    </div>
                )}

                {mainTab === "sensors" && usingMock && (
                    <div className="room-section" style={{ marginTop: 20, padding: "12px 16px", color: "#9ca3af" }}>
                        Sensor metrics are unavailable in frontend mock mode. Start backend sim mode to see live sensor metrics.
                    </div>
                )}

            </main>


            <SidePanel
                isOpen={sidePanelOpen}
                mode={sidePanelMode}
                onClose={() => setSidePanelOpen(false)}
                panels={panels}
                groups={groups}
                onGroupCreate={createGroup}
                onGroupUpdate={updateGroup}
                onGroupDelete={deleteGroup}
                targetRoutineId={targetRoutineId}
            />

            <LogsPanel
                isOpen={logsPanelOpen}
                onClose={() => setLogsPanelOpen(false)}
                auditLogs={auditLogs}
                loading={logsLoading}
                error={logsError}
                onRefresh={loadAuditLogs}
                isMock={usingMock}
                sensors={sensors}
                onRoutineLinkClick={(routineId) => {
                    setTargetRoutineId(routineId);
                    setSidePanelMode("routines");
                    setSidePanelOpen(true);
                    setLogsPanelOpen(false);
                }}
            />

        </>
    );
}

