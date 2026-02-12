import React, { useState, useRef, useCallback, useEffect } from "react";
import {
    runRoutine,
    startInterval,
    type RoutineRunResult,
    type IntervalHandle,
} from "../utils/routineEngine";
import type { Panel, Group } from "../types";

/* ---------- localStorage helpers ---------- */

const STORAGE_KEY = "glazing_saved_routines";

type SavedRoutine = { name: string; code: string };

function loadSavedRoutines(): SavedRoutine[] {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        return raw ? JSON.parse(raw) : [];
    } catch {
        return [];
    }
}

function persistRoutines(routines: SavedRoutine[]) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(routines));
}

/* ---------- example snippets ---------- */

const EXAMPLES: { label: string; code: string }[] = [
    {
        label: "If lux > 80, tint Right Group to 50%",
        code: `const lux = await sensors.getLatest("KM1-00", "lux");
log("Current lux: " + lux);

if (lux !== null && lux > 80) {
  await groups.setLevel("G-right", 50);
  log("High lux — tinted Right Group to 50%");
} else {
  log("Lux is fine, no action needed");
}`,
    },
    {
        label: "Set all panels to 0% (clear)",
        code: `const allPanels = await panels.list();
for (const p of allPanels) {
  await panels.setLevel(p.id, 0);
}
log("All panels cleared to 0%");`,
    },
    {
        label: "Log all sensor readings",
        code: `const sensorList = await sensors.list();
log("Found " + sensorList.length + " sensor(s)");

for (const s of sensorList) {
  const val = await sensors.getLatest(s.id, "lux");
  log(s.label + " (" + s.id + "): lux = " + val);
}`,
    },
];

/* ---------- component ---------- */

type Props = {
    panels: Panel[];
    groups: Group[];
};

type RunStatus = "idle" | "running" | "error" | "done";

export default function RoutineCodeEditor({ panels, groups }: Props) {
    const [code, setCode] = useState("");
    const [routineName, setRoutineName] = useState("");
    const [mode, setMode] = useState<"once" | "interval">("once");
    const [intervalMs, setIntervalMs] = useState(5000);
    const [indefinite, setIndefinite] = useState(false);
    const [status, setStatus] = useState<RunStatus>("idle");
    const [consoleLines, setConsoleLines] = useState<string[]>([]);
    const [iteration, setIteration] = useState(0);
    const [savedRoutines, setSavedRoutines] = useState<SavedRoutine[]>(loadSavedRoutines);
    const [showExamples, setShowExamples] = useState(false);

    const intervalRef = useRef<IntervalHandle | null>(null);
    const consoleEndRef = useRef<HTMLDivElement>(null);

    // Auto-scroll console
    useEffect(() => {
        consoleEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [consoleLines]);

    /* ---- run once ---- */
    const handleRunOnce = useCallback(async () => {
        if (!code.trim()) return;
        setStatus("running");
        setConsoleLines(["▶ Running routine..."]);
        setIteration(0);

        const result = await runRoutine(code);
        const lines = [...result.logs];
        if (result.error) {
            lines.push(`❌ Error: ${result.error}`);
            setStatus("error");
        } else {
            lines.push(`✅ Done (${result.durationMs.toFixed(0)}ms, ${result.actions.length} action(s))`);
            setStatus("done");
        }
        setConsoleLines(lines);
    }, [code]);

    /* ---- interval ---- */
    const handleStartInterval = useCallback(() => {
        if (!code.trim()) return;
        setStatus("running");
        setConsoleLines(["▶ Starting interval routine (every " + intervalMs + "ms)..."]);
        setIteration(0);

        const handle = startInterval(
            code,
            intervalMs,
            (result: RoutineRunResult, iter: number) => {
                setIteration(iter);
                setConsoleLines((prev) => {
                    const newLines = [...prev, `--- iteration ${iter} ---`, ...result.logs];
                    if (result.error) {
                        newLines.push(`❌ Error: ${result.error}`);
                        setStatus("error");
                        handle.stop();
                    }
                    // Keep console from growing too large
                    return newLines.slice(-500);
                });
            },
            { indefinite }
        );
        intervalRef.current = handle;
    }, [code, intervalMs, indefinite]);

    const handleStop = useCallback(() => {
        if (intervalRef.current) {
            intervalRef.current.stop();
            intervalRef.current = null;
        }
        setConsoleLines((prev) => [...prev, "⏹ Routine stopped"]);
        setStatus("idle");
    }, []);

    /* ---- save / load ---- */
    const handleSave = useCallback(() => {
        const name = routineName.trim() || `Routine ${savedRoutines.length + 1}`;
        const updated = [...savedRoutines.filter((r) => r.name !== name), { name, code }];
        setSavedRoutines(updated);
        persistRoutines(updated);
    }, [routineName, code, savedRoutines]);

    const handleLoad = useCallback(
        (name: string) => {
            const found = savedRoutines.find((r) => r.name === name);
            if (found) {
                setCode(found.code);
                setRoutineName(found.name);
            }
        },
        [savedRoutines]
    );

    const handleDelete = useCallback(
        (name: string) => {
            const updated = savedRoutines.filter((r) => r.name !== name);
            setSavedRoutines(updated);
            persistRoutines(updated);
        },
        [savedRoutines]
    );

    const handleInsertExample = (exampleCode: string) => {
        setCode(exampleCode);
        setShowExamples(false);
    };

    const isRunning = status === "running";

    return (
        <div className="routine-code-editor">
            {/* name */}
            <div className="form-group">
                <label>Routine Name</label>
                <input
                    type="text"
                    value={routineName}
                    onChange={(e) => setRoutineName(e.target.value)}
                    placeholder="e.g., Lux Auto-Tint"
                    disabled={isRunning}
                />
            </div>

            {/* editor */}
            <div className="form-group">
                <div className="routine-editor-toolbar">
                    <label>Script</label>
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
                        placeholder={`// Write your routine here\nconst lux = await sensors.getLatest("KM1-00", "lux");\nlog("Lux is " + lux);`}
                        rows={14}
                        spellCheck={false}
                        disabled={isRunning}
                    />
                </div>
            </div>

            {/* mode & controls */}
            <div className="routine-controls">
                <div className="routine-mode-toggle">
                    <button
                        className={`routine-mode-btn ${mode === "once" ? "active" : ""}`}
                        onClick={() => setMode("once")}
                        disabled={isRunning}
                        type="button"
                    >
                        Run Once
                    </button>
                    <button
                        className={`routine-mode-btn ${mode === "interval" ? "active" : ""}`}
                        onClick={() => setMode("interval")}
                        disabled={isRunning}
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
                                disabled={isRunning}
                            />
                            ms
                        </label>
                        <label className="routine-indefinite-label">
                            <input
                                type="checkbox"
                                checked={indefinite}
                                onChange={(e) => setIndefinite(e.target.checked)}
                                disabled={isRunning}
                            />
                            Run indefinitely
                        </label>
                        {!indefinite && (
                            <span className="routine-max-hint">Max: 1 hour</span>
                        )}
                    </div>
                )}

                <div className="routine-action-buttons">
                    {!isRunning ? (
                        <button
                            className="side-panel-action-btn"
                            onClick={mode === "once" ? handleRunOnce : handleStartInterval}
                            disabled={!code.trim()}
                            type="button"
                        >
                            ▶ Run
                        </button>
                    ) : (
                        <button
                            className="routine-stop-btn"
                            onClick={handleStop}
                            type="button"
                        >
                            ⏹ Stop
                        </button>
                    )}
                    <button
                        className="side-panel-secondary-btn"
                        onClick={handleSave}
                        disabled={!code.trim() || isRunning}
                        type="button"
                    >
                        Save
                    </button>
                </div>
            </div>

            {/* status */}
            <div className="routine-status-bar">
                <span className={`routine-status-badge routine-status-${status}`}>
                    {status === "idle" && "● Idle"}
                    {status === "running" && "● Running"}
                    {status === "error" && "● Error"}
                    {status === "done" && "● Done"}
                </span>
                {isRunning && mode === "interval" && (
                    <span className="routine-iteration-count">Iteration {iteration}</span>
                )}
            </div>

            {/* console output */}
            <div className="routine-console">
                <div className="routine-console-header">Console Output</div>
                <div className="routine-console-body">
                    {consoleLines.length === 0 ? (
                        <div className="routine-console-empty">
                            Output will appear here when you run a routine
                        </div>
                    ) : (
                        consoleLines.map((line, i) => (
                            <div
                                key={i}
                                className={`routine-console-line ${line.startsWith("❌") ? "error" : line.startsWith("✅") ? "success" : ""
                                    }`}
                            >
                                {line}
                            </div>
                        ))
                    )}
                    <div ref={consoleEndRef} />
                </div>
            </div>

            {/* saved routines */}
            <div className="routine-saved-section">
                <div className="routine-saved-header">Saved Routines</div>
                <div className="routine-saved-list">
                    {savedRoutines.length === 0 ? (
                        <div className="routine-saved-empty">
                            No saved routines yet — name your routine and click Save
                        </div>
                    ) : (
                        savedRoutines.map((r) => (
                            <div key={r.name} className="routine-saved-item">
                                <span className="routine-saved-name">{r.name}</span>
                                <div className="routine-saved-actions">
                                    <button
                                        className="routine-saved-load"
                                        onClick={() => handleLoad(r.name)}
                                        disabled={isRunning}
                                        type="button"
                                    >
                                        Load
                                    </button>
                                    <button
                                        className="routine-saved-delete"
                                        onClick={() => handleDelete(r.name)}
                                        disabled={isRunning}
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
