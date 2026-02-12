/**
 * Routine Engine — sandboxed script execution for glazing control routines.
 *
 * Scripts run inside an AsyncFunction with a whitelisted API:
 *   sensors.getLatest(sensorId, metric)  →  latest reading value
 *   sensors.list()                       →  all sensor info
 *   panels.list()                        →  all panels
 *   panels.setLevel(panelId, level)      →  set panel tint
 *   groups.list()                        →  all groups
 *   groups.setLevel(groupId, level)      →  set group tint
 *   log(message)                         →  write to console output
 */

import { api } from "../api";

/* ---------- public types ---------- */

export type RoutineAction = {
    type: "panel" | "group";
    target: string;
    level: number;
    result: string;
    ts: number;
};

export type RoutineRunResult = {
    logs: string[];
    actions: RoutineAction[];
    error?: string;
    durationMs: number;
};

export type IntervalHandle = {
    id: number;
    stop: () => void;
};

/* ---------- friendly error rewriting ---------- */

const FRIENDLY_HINTS: [RegExp, (m: RegExpMatchArray) => string][] = [
    [/(\w+) is not defined/i, (m: RegExpMatchArray) => `Unknown variable "${m[1]}" — did you forget to declare it with "const"?`],
    [/(\w+) is not a function/i, (m: RegExpMatchArray) => `"${m[1]}" is not a function — check spelling (available: getLatest, list, setLevel)`],
    [/Cannot read propert/i, () => "Tried to read a property on an undefined value — check that the variable exists"],
    [/Unexpected token/i, () => "Syntax error — check for missing brackets, quotes, or semicolons"],
    [/Unexpected end of input/i, () => "Unexpected end of script — you may be missing a closing } or )"],
];

function friendlyError(err: unknown): string {
    const raw = err instanceof Error ? err.message : String(err);
    for (const [pattern, rewrite] of FRIENDLY_HINTS) {
        const m = raw.match(pattern);
        if (m) return rewrite(m);
    }
    return raw;
}

/* ---------- sandbox builder ---------- */

function buildSandboxApi(logs: string[], actions: RoutineAction[]) {
    const log = (...args: unknown[]) => {
        const line = args.map((a) => (typeof a === "object" ? JSON.stringify(a) : String(a))).join(" ");
        logs.push(line);
    };

    const sensors = {
        async getLatest(sensorId: string, metric: string): Promise<number | null> {
            const all = await api.getLatestMetrics();
            const match = all.find((r) => r.sensor_id === sensorId && r.metric === metric);
            return match ? match.value : null;
        },
        async list() {
            return api.listSensors();
        },
    };

    const panels = {
        async list() {
            return api.panels();
        },
        async setLevel(panelId: string, level: number) {
            const result = await api.setPanelLevel(panelId, level);
            const action: RoutineAction = {
                type: "panel",
                target: panelId,
                level,
                result: result.message,
                ts: Date.now(),
            };
            actions.push(action);
            log(`✓ Panel ${panelId} → ${level}%`);
            return result;
        },
    };

    const groups = {
        async list() {
            return api.groups();
        },
        async setLevel(groupId: string, level: number) {
            const result = await api.setGroupLevel(groupId, level);
            const action: RoutineAction = {
                type: "group",
                target: groupId,
                level,
                result: result.message,
                ts: Date.now(),
            };
            actions.push(action);
            log(`✓ Group ${groupId} → ${level}%`);
            return result;
        },
    };

    return { log, sensors, panels, groups };
}

/* ---------- single run ---------- */

export async function runRoutine(code: string): Promise<RoutineRunResult> {
    const logs: string[] = [];
    const actions: RoutineAction[] = [];
    const start = performance.now();

    try {
        const sandbox = buildSandboxApi(logs, actions);

        // Build an async function with the user code. Only the sandbox vars are in scope.
        const AsyncFunction = Object.getPrototypeOf(async function () { }).constructor;
        const fn: (...args: unknown[]) => Promise<void> = new AsyncFunction(
            "sensors",
            "panels",
            "groups",
            "log",
            code
        );

        await fn(sandbox.sensors, sandbox.panels, sandbox.groups, sandbox.log);

        return { logs, actions, durationMs: performance.now() - start };
    } catch (err) {
        return {
            logs,
            actions,
            error: friendlyError(err),
            durationMs: performance.now() - start,
        };
    }
}

/* ---------- interval runner ---------- */

const DEFAULT_MAX_DURATION_MS = 60 * 60 * 1000; // 1 hour

export function startInterval(
    code: string,
    intervalMs: number,
    onTick: (result: RoutineRunResult, iteration: number) => void,
    options?: { maxDurationMs?: number; indefinite?: boolean }
): IntervalHandle {
    const maxDuration = options?.indefinite ? Infinity : (options?.maxDurationMs ?? DEFAULT_MAX_DURATION_MS);
    const startTime = Date.now();
    let iteration = 0;
    let stopped = false;

    const tick = async () => {
        if (stopped) return;

        // Check max duration
        if (Date.now() - startTime >= maxDuration) {
            onTick(
                {
                    logs: ["⏱ Routine reached maximum duration — automatically stopped"],
                    actions: [],
                    durationMs: Date.now() - startTime,
                },
                iteration
            );
            stopped = true;
            return;
        }

        iteration++;
        const result = await runRoutine(code);
        if (!stopped) {
            onTick(result, iteration);
        }
    };

    // Run immediately, then on interval
    tick();
    const id = window.setInterval(tick, intervalMs);

    return {
        id,
        stop() {
            stopped = true;
            window.clearInterval(id);
        },
    };
}
