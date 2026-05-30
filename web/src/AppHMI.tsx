import React, { useEffect, useRef, useState } from "react"
import { api } from "./api";
import { Panel, Group, AuditLogEntry } from "./types"
import { mockApi } from "./mockData";
import RoomGrid from "./components/RoomGrid";
import RoomGridCompact from "./components/RoomGridCompact";
import SidePanel from "./components/SidePanel";
import ActiveControllersBar from "./components/ActiveControllersBar";
import { controlManager, type ControlSource } from "./utils/controlManager";
import { useToast } from "./utils/toast";
import LogsPanel from "./components/LogsPanel";
import { Link } from "react-router-dom";
import LiveGraph from "./components/LiveGraph";
import { type SensorInfo, type SensorReadingResponse } from "./api";
import {
    connectedSensors as getConnectedSensors,
    getFreshMetricsForSensor,
    pruneVisibleSensorIds,
    sortSensorsForDisplay,
} from "./utils/sensorDisplay";
import SpectralGraph from "./components/SpectralGraph";

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

const METRIC_AXIS_LABELS: Record<string, string> = {
    lux: "Illuminance (lx)",
    cie1931_x: "CIE 1931 x",
    cie1931_y: "CIE 1931 y",
    s_cone_irradiance_mw_m2: "S-cone irradiance (mW/m2)",
    m_cone_irradiance_mw_m2: "M-cone irradiance (mW/m2)",
    l_cone_irradiance_mw_m2: "L-cone irradiance (mW/m2)",
    rhodopic_irradiance_mw_m2: "Rhodopic irradiance (mW/m2)",
    melanopic_irradiance_mw_m2: "Melanopic irradiance (mW/m2)",
    s_cone_edi_lx: "S-cone EDI (lx)",
    m_cone_edi_lx: "M-cone EDI (lx)",
    l_cone_edi_lx: "L-cone EDI (lx)",
    rhodopic_edi_lx: "Rhodopic EDI (lx)",
    melanopic_edi_lx: "Melanopic EDI (lx)",
    cct_ohno_k: "CCT Ohno (K)",
    cct_robertson_k: "CCT Robertson (K)",
    cri_ra: "CRI Ra",
    cfi_rf: "CFI Rf",
    duv_ohno: "Duv Ohno",
    duv_robertson: "Duv Robertson",
    sample_interval_s: "Sample interval (s)",
    lux_calc: "Calculated illuminance (lx)",
    board_temp_c: "Board temp (degC)",
    sensor_temp_c: "Sensor temp (degC)",
    ghi_w_m2: "GHI (W/m2)",
    dni_w_m2: "DNI (W/m2)",
    dhi_w_m2: "DHI (W/m2)",
    latitude_deg: "Latitude (deg)",
    longitude_deg: "Longitude (deg)",
    sun_elevation_deg: "Sun elevation (deg)",
    sun_azimuth_deg: "Sun azimuth (deg)",
    gps_timestamp_s: "GPS time (s)",
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

function metricAxisLabel(metric: string): string {
    return METRIC_AXIS_LABELS[metric] || METRIC_LABELS[metric] || metric;
}

function sensorGraphHeight(kind: string): number {
    return kind === "jeti_spectraval" || kind === "eko_ms90_plus" ? 420 : 260;
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

function formatMetricTimestamp(ts: number): string {
    return new Date(ts * 1000).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
    });
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
    const [docsDropdownOpen, setDocsDropdownOpen] = useState<boolean>(false);
    const docsDropdownRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        function handleClickOutside(event: MouseEvent) {
            if (docsDropdownRef.current && !docsDropdownRef.current.contains(event.target as Node)) {
                setDocsDropdownOpen(false);
            }
        }
        document.addEventListener("mousedown", handleClickOutside);
        return () => {
            document.removeEventListener("mousedown", handleClickOutside);
        };
    }, []);

    const [spectralModal, setSpectralModal] = useState<{ sensorId: string; fixedTs?: number } | null>(null);

    const connectedSensorList = sortSensorsForDisplay(getConnectedSensors(sensors, latestMetrics));
    const sensorListForControls = connectedSensorList.length > 0 ? connectedSensorList : sortSensorsForDisplay(sensors);
    const sensorIdsForControls = sensorListForControls.map(sensor => sensor.id);
    const sensorControlKey = sensorIdsForControls.join("|");
    const showingConfiguredSensorsFallback = sensors.length > 0 && connectedSensorList.length === 0;
    const selectedGroup = groups.find(g => g.id === groupId);
    const highlightedPanelIds = new Set(selectedGroup?.member_ids || []);


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
                setSensors([]);
                setLatestMetrics([]);

                if (g.length) {
                    setGroupId(prev => prev || g[0].id);
                }

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
        if (!sensorIdsForControls.length) {
            setVisibleSensorIds([]);
            return;
        }

        if (!sensorVisibilityUserSet.current) {
            setVisibleSensorIds(sensorIdsForControls);
            return;
        }

        setVisibleSensorIds(prev => pruneVisibleSensorIds(prev, sensorIdsForControls));
    }, [sensorControlKey]);

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

    const visibleSensors = sensorListForControls.filter(sensor => visibleSensorIds.includes(sensor.id));
    const hideSensor = (sensorId: string) => {
        sensorVisibilityUserSet.current = true;
        setVisibleSensorIds(prev => prev.filter(id => id !== sensorId));
    };


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

                        <div className={`hmi-dropdown ${docsDropdownOpen ? "open" : ""}`} ref={docsDropdownRef}>
                            <Link to="/docs" style={{ textDecoration: "none" }}>
                                <button
                                    className="hmi-manage-btn"
                                    title="View Docs"
                                    style={{ display: "flex", alignItems: "center", gap: "6px" }}
                                >
                                    Docs
                                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor" className="hmi-dropdown-arrow">
                                        <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
                                    </svg>
                                </button>
                            </Link>
                            <div className="hmi-dropdown-menu">
                                <Link to="/docs" className="hmi-dropdown-item" onClick={() => setDocsDropdownOpen(false)}>
                                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25" />
                                    </svg>
                                    General Docs
                                </Link>
                                <Link to="/docs/sensors" target="_blank" rel="noopener noreferrer" className="hmi-dropdown-item" onClick={() => setDocsDropdownOpen(false)}>
                                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12a7.5 7.5 0 0015 0m-15 0a7.5 7.5 0 1115 0m-15 0H3m16.5 0H21m-1.5 0H12m-8.457 3.077l1.41-.513m14.095-5.13l1.41-.513M5.106 17.785l1.15-.827m11.379-8.16l1.15-.827M8.14 21.27l.707-1.03m7.45-10.86l.707-1.03M12 3v1.5m0 15V21m-9-9h1.5m12 0H21" />
                                    </svg>
                                    Sensor Setup & Quickstart
                                </Link>
                                <Link to="/docs/routines" target="_blank" rel="noopener noreferrer" className="hmi-dropdown-item" onClick={() => setDocsDropdownOpen(false)}>
                                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" d="M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 16.5" />
                                    </svg>
                                    Routine Developer Docs
                                </Link>
                            </div>
                        </div>


                    </div>
                </div>
            </header>

            <main className={`hmi-main ${sidePanelOpen ? 'with-side-panel' : ''}`}>
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

                {mainTab === "sensors" && (
                    <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "16px", marginBottom: "-4px" }}>
                        <Link to="/docs/sensors" target="_blank" rel="noopener noreferrer">
                            <button
                                className="hmi-manage-btn"
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: "8px",
                                    background: "linear-gradient(135deg, rgba(30, 64, 175, 0.25) 0%, rgba(37, 99, 235, 0.2) 100%)",
                                    border: "1px solid rgba(59, 130, 246, 0.4)",
                                    color: "#93c5fd",
                                    fontSize: "13px",
                                    fontWeight: "600",
                                    boxShadow: "0 2px 6px rgba(0, 0, 0, 0.15)"
                                }}
                                title="View Sensor Connection & Setup Quickstart Guide"
                            >
                                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" style={{ width: "16px", height: "16px" }}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25" />
                                </svg>
                                Sensor Docs/Quickstart
                            </button>
                        </Link>
                    </div>
                )}

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
                                    value={groupId}
                                    onChange={e => setGroupId(e.target.value)}
                                    style={{ padding: '4px 8px' }}
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
                                    style={{ width: 80, padding: '4px 8px' }}
                                />

                                <button
                                    className="hmi-manage-btn"
                                    onClick={() => groupId && setGroup(groupId, groupLevel)}
                                    disabled={!groupId || busy === groupId}
                                    title="Set selected group level"
                                    style={{ padding: '4px 10px' }}
                                >
                                    {busy === groupId ? 'Setting…' : 'Tint Group'}
                                </button>


                            </div>
                        </div>

                        {/* room grids */}
                        {sidePanelOpen ? (
                            <RoomGridCompact
                                panels={panels}
                                transitioning={transitioning}
                                panelControls={controlState.panelControls}
                                highlightedPanelIds={highlightedPanelIds}
                            />
                        ) : (
                            <RoomGrid
                                panels={panels}
                                onSet={setPanel}
                                busyId={busy}
                                transitioning={transitioning}
                                panelControls={controlState.panelControls}
                                highlightedPanelIds={highlightedPanelIds}
                            />
                        )}

                    </>
                )}

                {/* Sensor Metrics + Live Graph Section */}
                {mainTab === "sensors" && !usingMock && sensorListForControls.length > 0 && (
                    <div className="room-section sensor-visibility-card" style={{ marginTop: 20 }}>
                        <div className="room-header">
                            <h2 className="room-title">Visible sensors</h2>
                            <div className="room-stats">
                                <span>{visibleSensors.length} of {sensorListForControls.length} shown</span>
                                {showingConfiguredSensorsFallback && <span style={{ marginLeft: 8 }}>configured</span>}
                            </div>
                        </div>
                        <div className="sensor-visibility-body">
                            <div className="sensor-visibility-list" aria-label="Visible sensors">
                                {sensorListForControls.map(sensor => {
                                    const active = visibleSensorIds.includes(sensor.id);
                                    const sensorKindLabel = SENSOR_KIND_LABELS[sensor.kind] || sensor.kind;
                                    return (
                                        <label
                                            key={`visibility-${sensor.id}`}
                                            className={`sensor-visibility-row ${active ? "active" : ""}`}
                                            title={`${sensor.label || sensor.id} (${sensorKindLabel})`}
                                        >
                                            <input
                                                type="checkbox"
                                                checked={active}
                                                onChange={() => {
                                                    sensorVisibilityUserSet.current = true;
                                                    setVisibleSensorIds(prev =>
                                                        prev.includes(sensor.id)
                                                            ? prev.filter(id => id !== sensor.id)
                                                            : [...prev, sensor.id]
                                                    );
                                                }}
                                            />
                                            <span className="sensor-visibility-name">{sensor.label || sensor.id}</span>
                                            <span className="sensor-visibility-kind">{sensorKindLabel}</span>
                                        </label>
                                    );
                                })}
                            </div>
                            <div className="sensor-visibility-actions">
                                <button
                                    className="sensor-visibility-action"
                                    onClick={() => {
                                        sensorVisibilityUserSet.current = true;
                                        setVisibleSensorIds(sensorIdsForControls);
                                    }}
                                >
                                    All
                                </button>
                                <button
                                    className="sensor-visibility-action"
                                    onClick={() => {
                                        sensorVisibilityUserSet.current = true;
                                        setVisibleSensorIds([]);
                                    }}
                                >
                                    None
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                {mainTab === "sensors" && !usingMock && visibleSensors.map(sensor => {
                    const sensorMetrics = getFreshMetricsForSensor(sensor, latestMetrics);
                    const metricMap = new Map<string, SensorReadingResponse>();
                    sensorMetrics.forEach(m => metricMap.set(m.metric, m));
                    const metricNames = Array.from(metricMap.keys());
                    const orderedMetricNames = orderMetrics(sensor.kind, metricNames);
                    const availableGraphMetrics = graphMetricOptions(sensor.kind, metricNames);
                    const requestedMetric = graphMetricBySensor[sensor.id];
                    const selectedGraphMetric = requestedMetric && availableGraphMetrics.includes(requestedMetric)
                        ? requestedMetric
                        : availableGraphMetrics[0] || "";
                    const selectedReading = selectedGraphMetric ? metricMap.get(selectedGraphMetric) : undefined;
                    const sensorKindLabel = SENSOR_KIND_LABELS[sensor.kind] || sensor.kind;
                    const graphHeight = sensorGraphHeight(sensor.kind);

                    if (!selectedGraphMetric || !selectedReading) {
                        return (
                            <div key={sensor.id} className="room-section sensor-card sensor-card-no-data" style={{ marginTop: 20 }}>
                                <div className="room-header sensor-card-header">
                                    <h2 className="room-title">{sensor.label || sensor.id}</h2>
                                    <div className="room-stats">
                                        <span>{sensorKindLabel}</span>
                                        {sensor.location && <span style={{ marginLeft: 8 }}>{sensor.location}</span>}
                                        <span style={{ marginLeft: 8 }}>not reporting</span>
                                        {sensor.kind === "jeti_spectraval" && (
                                            <button
                                                className="hmi-manage-btn"
                                                onClick={() => setSpectralModal({ sensorId: sensor.id })}
                                                style={{ marginLeft: 12, marginRight: 8, padding: "2px 8px", fontSize: "11px", height: "auto" }}
                                                title="View real-time spectral irradiance graph"
                                            >
                                                View Spectrum
                                            </button>
                                        )}
                                        <button
                                            type="button"
                                            className="sensor-card-hide-btn"
                                            onClick={() => hideSensor(sensor.id)}
                                            title={`Hide ${sensor.label || sensor.id}`}
                                        >
                                            Hide
                                        </button>
                                    </div>
                                </div>
                                <div className="sensor-card-layout">
                                    <div className="sensor-metrics-panel">
                                        <div className="sensor-metrics-heading">Live metrics</div>
                                        <div className="sensor-empty-state">No live data yet</div>
                                    </div>
                                    <div className="sensor-graph-panel">
                                        <div className="sensor-empty-state sensor-empty-graph" style={{ height: graphHeight }}>
                                            Graph appears when readings arrive
                                        </div>
                                    </div>
                                </div>
                            </div>
                        );
                    }

                    return (
                        <div key={sensor.id} className="room-section sensor-card" style={{ marginTop: 20 }}>
                            <div className="room-header sensor-card-header">
                                <h2 className="room-title">{sensor.label || sensor.id}</h2>
                                <div className="room-stats">
                                    <span>{sensorKindLabel}</span>
                                    {sensor.location && <span style={{ marginLeft: 8 }}>{sensor.location}</span>}
                                    <span style={{ marginLeft: 8 }}>{orderedMetricNames.length} metrics</span>
                                    {sensor.kind === "jeti_spectraval" && (
                                        <button
                                            className="hmi-manage-btn"
                                            onClick={() => setSpectralModal({ sensorId: sensor.id })}
                                            style={{ marginLeft: 12, marginRight: 8, padding: "2px 8px", fontSize: "11px", height: "auto" }}
                                            title="View real-time spectral irradiance graph"
                                        >
                                            View Spectrum
                                        </button>
                                    )}
                                    <button
                                        type="button"
                                        className="sensor-card-hide-btn"
                                        onClick={() => hideSensor(sensor.id)}
                                        title={`Hide ${sensor.label || sensor.id}`}
                                    >
                                        Hide
                                    </button>
                                </div>
                            </div>

                            <div className="sensor-card-layout">
                                <div className="sensor-metrics-panel">
                                    <div className="sensor-metrics-heading">Live metrics</div>
                                    <div className="sensor-metrics-grid">
                                        {orderedMetricNames.map(metric => {
                                            const reading = metricMap.get(metric);
                                            if (!reading) return null;
                                            const isSelected = metric === selectedGraphMetric;

                                            return (
                                                <button
                                                    key={`${sensor.id}-${metric}`}
                                                    type="button"
                                                    className={`sensor-metric-row ${isSelected ? "active" : ""}`}
                                                    aria-pressed={isSelected}
                                                    onClick={() => {
                                                        if (availableGraphMetrics.includes(metric)) {
                                                            setGraphMetricBySensor(prev => ({ ...prev, [sensor.id]: metric }));
                                                        }
                                                    }}
                                                >
                                                    <span className="sensor-metric-label">
                                                        {METRIC_LABELS[metric] || metric}
                                                    </span>
                                                    <span className="sensor-metric-value">
                                                        {formatMetricValue(metric, reading.value)}
                                                    </span>
                                                </button>
                                            );
                                        })}
                                    </div>
                                    <div className="sensor-metrics-meta">
                                        Graphing {METRIC_LABELS[selectedGraphMetric] || selectedGraphMetric} - updated {formatMetricTimestamp(selectedReading.ts)}
                                    </div>
                                </div>

                                <div className="sensor-graph-panel">
                                    {availableGraphMetrics.length > 1 && (
                                        <div className="sensor-graph-controls">
                                            <label className="hmi-status-label">Graph metric</label>
                                            <select
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
                                    )}
                                    <LiveGraph
                                        sensorId={sensor.id}
                                        metric={selectedGraphMetric}
                                        label={`${sensor.label || sensor.id} - ${METRIC_LABELS[selectedGraphMetric] || selectedGraphMetric}`}
                                        yAxisLabel={metricAxisLabel(selectedGraphMetric)}
                                        valueFormatter={(value) => value != null ? formatMetricValue(selectedGraphMetric, value) : "N/A"}
                                        color={sensorGraphColor(sensor.kind)}
                                        height={graphHeight}
                                        variant="embedded"
                                    />
                                </div>
                            </div>
                        </div>
                    );
                })}

                {mainTab === "sensors" && !usingMock && sensorListForControls.length > 0 && visibleSensors.length === 0 && (
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
                onViewSpectrum={(sensorId, ts) => {
                    setSpectralModal({ sensorId, fixedTs: ts });
                }}
            />

            {spectralModal && (
                <>
                    <div className="side-panel-overlay" onClick={() => setSpectralModal(null)} style={{ zIndex: 1200 }} />
                    <div
                        className="logs-modal"
                        role="dialog"
                        aria-modal="true"
                        style={{
                            zIndex: 1201,
                            maxWidth: "800px",
                            height: "auto",
                            minHeight: "520px",
                        }}
                        onClick={e => e.stopPropagation()}
                    >
                        <div className="logs-modal-header">
                            <h2>
                                Spectral Irradiance - {spectralModal.sensorId} 
                                {spectralModal.fixedTs ? ` (${new Date(spectralModal.fixedTs * 1000).toLocaleString()})` : " (Live)"}
                            </h2>
                            <button
                                className="logs-modal-close"
                                onClick={() => setSpectralModal(null)}
                                aria-label="Close spectrum"
                            >
                                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" style={{ width: "20px", height: "20px" }}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                                </svg>
                            </button>
                        </div>
                        <div className="logs-panel-content" style={{ padding: "20px 24px" }}>
                            <SpectralGraph sensorId={spectralModal.sensorId} fixedTs={spectralModal.fixedTs} />
                        </div>
                    </div>
                </>
            )}

        </>
    );
}

