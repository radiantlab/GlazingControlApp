import React, { useState, useRef, useCallback, useEffect } from "react";
import { Link } from "react-router-dom";
import { API_BASE } from "../api";
import type { Panel, Group } from "../types";

/* ---------- Types ---------- */

type RoutineStatus = "idle" | "scheduled" | "running" | "error" | "done" | "stopped";

type RoutineStatusResponse = {
    id: string;
    name: string;
    code: string;
    mode: "once" | "interval";
    interval_ms?: number;
    run_at_ts?: number;
    indefinite: boolean;
    status: RoutineStatus;
    logs: string[];
    duration_ms?: number;
};

/* ---------- localStorage helpers ---------- */

type SavedRoutine = { name: string; code: string };

/* ---------- example snippets ---------- */

const EXAMPLES: { label: string; code: string }[] = [
    {
        label: "If lux > 80, tint Right Group to 50%",
        code: `lux = sensors.get_latest("KM1-00", "lux")
log(f"Current lux: {lux}")

if lux is not None and lux > 80:
    groups.set_level("G-right", 50)
    log("High lux — tinted Right Group to 50%")
else:
    log("Lux is fine, no action needed")`,
    },
    {
        label: "Use melanopic EDI from JETI",
        code: `const melEdi = await sensors.getLatest("JETI-00", "melanopic_edi_lx");
log("Melanopic EDI: " + melEdi);

if (melEdi !== null && melEdi > 120) {
  await groups.setLevel("G-facade", 70);
  log("High melanopic EDI - tinted facade to 70%");
}`,
    },
    {
        label: "Set all panels to 0% (clear)",
        code: `all_panels = panels.list()
for p in all_panels:
    panels.set_level(p["id"], 0)
log("All panels cleared to 0%")`,
    },
    {
        label: "Log all sensor readings",
        code: `sensor_list = sensors.list()
log(f"Found {len(sensor_list)} sensor(s)")

for s in sensor_list:
    val = sensors.get_latest(s["id"], "lux")
    log(f"{s['label']} ({s['id']}): lux = {val}")`,
    },
];

/* ---------- component ---------- */

type Props = {
    panels: Panel[];
    groups: Group[];
};

export default function RoutineCodeEditor({ panels, groups }: Props) {
    const [code, setCode] = useState("");
    const [routineName, setRoutineName] = useState("");
    const [mode, setMode] = useState<"once" | "interval">("once");
    const [runAtDate, setRunAtDate] = useState("");
    const [runAtTime, setRunAtTime] = useState("");
    const [intervalMs, setIntervalMs] = useState(5000);
    const [indefinite, setIndefinite] = useState(false);

    // Global active routines state
    const [activeRoutines, setActiveRoutines] = useState<RoutineStatusResponse[]>([]);
    const [focusedRoutineId, setFocusedRoutineId] = useState<string | null>(null);

    const [savedRoutines, setSavedRoutines] = useState<SavedRoutine[]>([]);
    const [showExamples, setShowExamples] = useState(false);

    const consoleEndRef = useRef<HTMLDivElement>(null);

    // Auto-scroll console
    const focusedRoutine = activeRoutines.find(r => r.id === focusedRoutineId);
    useEffect(() => {
        consoleEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [focusedRoutine?.logs]);

    // Polling loop
    useEffect(() => {
        const fetchRoutines = async () => {
            try {
                const res = await fetch(`${API_BASE}/routines`);
                if (res.ok) {
                    const data = await res.json();
                    setActiveRoutines(data);
                }
            } catch (err) {
                console.error("Failed to fetch routines", err);
            }
        };

        const fetchSavedRoutines = async () => {
            try {
                const res = await fetch(`${API_BASE}/saved-routines`);
                if (res.ok) {
                    const data = await res.json();
                    setSavedRoutines(data);
                }
            } catch (err) {
                console.error("Failed to fetch saved routines", err);
            }
        };

        fetchRoutines();
        fetchSavedRoutines();
        const interval = setInterval(fetchRoutines, 2000);
        return () => clearInterval(interval);
    }, []);

    /* ---- launch routine ---- */
    const handleLaunch = useCallback(async () => {
        if (!code.trim()) return;

        let runAtTs: number | undefined = undefined;
        if (runAtDate || runAtTime) {
            const tempRunAtDate = runAtDate || new Date().toISOString().split("T")[0];
            const tempRunAtTime = runAtTime || "00:00";
            let targetDate = new Date(`${tempRunAtDate}T${tempRunAtTime}`);

            // If only time was provided and it's already passed today, assume it's for tomorrow
            if (!runAtDate && runAtTime && targetDate.getTime() < Date.now()) {
                targetDate.setDate(targetDate.getDate() + 1);
            }
            runAtTs = targetDate.getTime() / 1000.0;
        }

        const name = routineName.trim() || `Routine ${new Date().toLocaleTimeString()}`;

        try {
            const res = await fetch(`${API_BASE}/routines`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    name,
                    code,
                    mode,
                    interval_ms: mode === "interval" ? intervalMs : undefined,
                    run_at_ts: runAtTs,
                    indefinite
                })
            });
            if (res.ok) {
                const data = await res.json();
                setFocusedRoutineId(data.id);
            }
        } catch (err) {
            console.error("Failed to launch routine", err);
        }
    }, [code, routineName, mode, intervalMs, runAtDate, runAtTime, indefinite]);


    const handleStop = useCallback(async (id: string) => {
        try {
            await fetch(`${API_BASE}/routines/${id}/stop`, { method: "POST" });
            // Optimistic update
            setActiveRoutines(prev => prev.map(r => r.id === id ? { ...r, status: "stopped" } : r));
        } catch (err) {
            console.error("Failed to stop routine", err);
        }
    }, []);

    const handleDeleteServerRoutine = useCallback(async (id: string) => {
        try {
            await fetch(`${API_BASE}/routines/${id}`, { method: "DELETE" });
            setActiveRoutines(prev => prev.filter(r => r.id !== id));
            if (focusedRoutineId === id) setFocusedRoutineId(null);
        } catch (err) {
            console.error("Failed to delete routine", err);
        }
    }, [focusedRoutineId]);


    /* ---- save / load ---- */
    const handleSaveServer = useCallback(async () => {
        const name = routineName.trim() || `Routine ${savedRoutines.length + 1}`;
        try {
            await fetch(`${API_BASE}/saved-routines`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name, code })
            });
            // Update local state to reflect the server without needing to re-fetch
            const updated = [...savedRoutines.filter((r) => r.name !== name), { name, code }];
            // Sort by name alphabetically
            updated.sort((a, b) => a.name.localeCompare(b.name));
            setSavedRoutines(updated);
        } catch (err) {
            console.error("Failed to save routine to server", err);
        }
    }, [routineName, code, savedRoutines]);

    const handleLoadServer = useCallback(
        (name: string) => {
            const found = savedRoutines.find((r) => r.name === name);
            if (found) {
                setCode(found.code);
                setRoutineName(found.name);
            }
        },
        [savedRoutines]
    );

    const handleDeleteServerSaved = useCallback(async (name: string) => {
        try {
            await fetch(`${API_BASE}/saved-routines/${encodeURIComponent(name)}`, { method: "DELETE" });
            const updated = savedRoutines.filter((r) => r.name !== name);
            setSavedRoutines(updated);
        } catch (err) {
            console.error("Failed to delete saved routine from server", err);
        }
    }, [savedRoutines]);

    const handleInsertExample = (exampleCode: string) => {
        setCode(exampleCode);
        setShowExamples(false);
    };

    return (
        <div className="routine-code-editor">
            {/* Active Routines List */}
            {activeRoutines.length > 0 && (
                <div style={{ marginBottom: 16, border: '1px solid var(--hmi-border-color)', borderRadius: '6px', overflow: 'hidden' }}>
                    <div style={{ background: 'var(--hmi-bg-panel)', padding: '8px 12px', fontWeight: 600, borderBottom: '1px solid var(--hmi-border-color)', fontSize: '13px' }}>
                        Active & Recent Routines
                    </div>
                    <div>
                        {activeRoutines.map(r => (
                            <div
                                key={r.id}
                                style={{
                                    padding: '8px 12px',
                                    borderBottom: '1px solid var(--hmi-border-color)',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'space-between',
                                    background: r.id === focusedRoutineId ? 'var(--hmi-bg-panel-hover)' : 'transparent',
                                    cursor: 'pointer'
                                }}
                                onClick={() => setFocusedRoutineId(r.id)}
                            >
                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                    <span className={`routine-status-badge routine-status-${r.status}`} style={{ zoom: 0.85 }}>
                                        ● {r.status}
                                    </span>
                                    <span style={{ fontWeight: 500, fontSize: '13px' }}>{r.name}</span>
                                    <span style={{ fontSize: '12px', color: 'var(--hmi-text-muted)' }}>
                                        ({r.mode})
                                    </span>
                                </div>
                                <div style={{ display: 'flex', gap: '6px' }}>
                                    {(r.status === "running" || r.status === "scheduled") && (
                                        <button
                                            className="routine-stop-btn"
                                            onClick={(e) => { e.stopPropagation(); handleStop(r.id); }}
                                            style={{ padding: '2px 8px', fontSize: '11px' }}
                                        >
                                            Stop
                                        </button>
                                    )}
                                    <button
                                        className="side-panel-secondary-btn"
                                        onClick={(e) => { e.stopPropagation(); handleDeleteServerRoutine(r.id); }}
                                        style={{ padding: '2px 8px', fontSize: '11px' }}
                                    >
                                        ✕
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* name */}
            <div className="form-group" style={{ position: 'relative' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <label>Routine Name</label>
                    <Link
                        to="/docs"
                        target="_blank"
                        style={{
                            fontSize: "12px",
                            fontWeight: 600,
                            color: "var(--btn-blue)",
                            textDecoration: "none",
                            padding: "2px 6px",
                            border: "1px solid var(--btn-blue)",
                            borderRadius: "4px"
                        }}
                    >
                        View Documentation ↗
                    </Link>
                </div>
                <input
                    type="text"
                    value={routineName}
                    onChange={(e) => setRoutineName(e.target.value)}
                    placeholder="e.g., Lux Auto-Tint"
                />
            </div>

            {/* editor */}
            <div className="form-group">
                <div className="routine-editor-toolbar">
                    <label>Script (Python)</label>
                    <button
                        className="routine-examples-toggle"
                        onClick={() => setShowExamples(!showExamples)}
                        type="button"
                    >
                        {showExamples ? "Hide Examples ▲" : "Examples ▼"}
                    </button>
                </div>

                {showExamples && (
                    <div className="routine-examples">
                        {EXAMPLES.map((ex, i) => (
                            <button
                                key={i}
                                className="routine-example-btn"
                                onClick={() => handleInsertExample(ex.code)}
                                type="button"
                            >
                                {ex.label}
                            </button>
                        ))}
                    </div>
                )}

                <div className="routine-textarea-wrapper">
                    <textarea
                        className="routine-code-textarea"
                        value={code}
                        onChange={(e) => setCode(e.target.value)}
                        placeholder={`# Write your python routine here\nlux = sensors.get_latest("KM1-00", "lux")\nlog(f"Lux is {lux}")`}
                        rows={14}
                        spellCheck={false}
                    />
                </div>
            </div>

            {/* mode & controls */}
            <div className="routine-controls">
                <div className="routine-mode-toggle">
                    <button
                        className={`routine-mode-btn ${mode === "once" ? "active" : ""}`}
                        onClick={() => setMode("once")}
                        type="button"
                    >
                        Run Once
                    </button>
                    <button
                        className={`routine-mode-btn ${mode === "interval" ? "active" : ""}`}
                        onClick={() => setMode("interval")}
                        type="button"
                    >
                        Run on Interval
                    </button>
                </div>

                {mode === "interval" && (
                    <div className="routine-interval-config">
                        <label>
                            Every
                            <input
                                type="number"
                                className="routine-interval-input"
                                value={intervalMs}
                                onChange={(e) => setIntervalMs(Math.max(1000, Number(e.target.value)))}
                                min={1000}
                                step={1000}
                            />
                            ms
                        </label>
                        <label className="routine-indefinite-label">
                            <input
                                type="checkbox"
                                checked={indefinite}
                                onChange={(e) => setIndefinite(e.target.checked)}
                            />
                            Run indefinitely
                        </label>
                        {!indefinite && (
                            <span className="routine-max-hint">Max: 1 hour</span>
                        )}
                    </div>
                )}

                <div className="routine-schedule-config" style={{ marginTop: 8, marginBottom: 8, display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                    <label style={{ fontSize: '13px', color: 'var(--hmi-text-muted)', fontWeight: 600 }}>
                        Run At <span style={{ fontWeight: 'normal' }}>(Optional)</span>
                    </label>
                    <input
                        type="date"
                        className="routine-interval-input"
                        value={runAtDate}
                        onChange={(e) => setRunAtDate(e.target.value)}
                        style={{ marginLeft: 4, width: 130 }}
                    />
                    <input
                        type="time"
                        className="routine-interval-input"
                        value={runAtTime}
                        onChange={(e) => setRunAtTime(e.target.value)}
                        style={{ width: 110 }}
                    />
                    {(runAtDate || runAtTime) && (
                        <button
                            type="button"
                            onClick={() => {
                                setRunAtDate("");
                                setRunAtTime("");
                            }}
                            className="side-panel-secondary-btn"
                            style={{ padding: '4px 8px', fontSize: '12px' }}
                        >
                            Clear
                        </button>
                    )}
                </div>

                <div className="routine-action-buttons">
                    <button
                        className="side-panel-action-btn"
                        onClick={handleLaunch}
                        disabled={!code.trim()}
                        type="button"
                    >
                        ▶ Launch Routine
                    </button>
                    <button
                        className="side-panel-secondary-btn"
                        onClick={handleSaveServer}
                        disabled={!code.trim()}
                        type="button"
                    >
                        Save to Server
                    </button>
                </div>
            </div>

            {/* console output for focused routine */}
            {focusedRoutineId && (
                <div className="routine-console" style={{ marginTop: 24 }}>
                    <div className="routine-console-header">
                        Console Output: {focusedRoutine?.name || "Unknown"}
                    </div>
                    <div className="routine-console-body">
                        {!focusedRoutine?.logs || focusedRoutine.logs.length === 0 ? (
                            <div className="routine-console-empty">
                                Waiting for output...
                            </div>
                        ) : (
                            focusedRoutine.logs.map((line, i) => (
                                <div
                                    key={i}
                                    className={`routine-console-line ${line.startsWith("❌") || line.toLowerCase().includes("error") ? "error" : line.startsWith("✅") || line.includes("✓") ? "success" : ""
                                        }`}
                                >
                                    {line}
                                </div>
                            ))
                        )}
                        <div ref={consoleEndRef} />
                    </div>
                </div>
            )}

            {/* saved routines */}
            <div className="routine-saved-section" style={{ marginTop: 24 }}>
                <div className="routine-saved-header">Saved Routines</div>
                <div className="routine-saved-list">
                    {savedRoutines.length === 0 ? (
                        <div className="routine-saved-empty">
                            No saved routines yet — name your routine and click Save to Server
                        </div>
                    ) : (
                        savedRoutines.map((r) => (
                            <div key={r.name} className="routine-saved-item">
                                <span className="routine-saved-name">{r.name}</span>
                                <div className="routine-saved-actions">
                                    <button
                                        className="routine-saved-load"
                                        onClick={() => handleLoadServer(r.name)}
                                        type="button"
                                    >
                                        Load
                                    </button>
                                    <button
                                        className="routine-saved-delete"
                                        onClick={() => handleDeleteServerSaved(r.name)}
                                        type="button"
                                    >
                                        ✕
                                    </button>
                                </div>
                            </div>
                        ))
                    )}
                </div>
            </div>
        </div>
    );
}
