import { spawn } from "node:child_process";
import { existsSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const repoRoot = path.resolve(path.dirname(__filename), "..");
const svcDir = path.join(repoRoot, "svc");
const webDir = path.join(repoRoot, "web");
const npmCommand = process.platform === "win32" ? "npm.cmd" : "npm";
const uvCommand = process.platform === "win32" ? "uv.exe" : "uv";
const allowedTargets = new Set(["backend", "frontend", "both"]);

const selected = process.argv[2]?.toLowerCase();
if (selected && !allowedTargets.has(selected)) {
    console.error("Usage: npm run watch -- [backend|frontend|both]");
    process.exit(1);
}

const target = selected ?? inferDefaultTarget(process.cwd());
console.log(`[watch] mode=${target}`);

let shuttingDown = false;
let frontendProcess = null;
let backendProcess = null;
let backendPollingTimer = null;
let backendRunInProgress = false;
let backendRunQueued = false;
let backendSnapshot = new Map();

start();

function start() {
    if (target === "frontend" || target === "both") {
        startFrontendWatcher();
    }

    if (target === "backend" || target === "both") {
        startBackendWatcher();
    }
}

function inferDefaultTarget(cwd) {
    const resolvedCwd = path.resolve(cwd);
    if (isPathInside(svcDir, resolvedCwd)) {
        return "backend";
    }

    if (isPathInside(webDir, resolvedCwd)) {
        return "frontend";
    }

    return "both";
}

function isPathInside(parentDir, candidateDir) {
    const parent = path.resolve(parentDir);
    const candidate = path.resolve(candidateDir);
    return candidate === parent || candidate.startsWith(`${parent}${path.sep}`);
}

function startFrontendWatcher() {
    if (!existsSync(path.join(webDir, "package.json"))) {
        console.error(`[watch] missing ${path.join(webDir, "package.json")}`);
        shutdown(1);
        return;
    }

    console.log("[watch:frontend] starting TypeScript watch");
    frontendProcess = spawn(npmCommand, ["run", "typecheck:watch"], {
        cwd: webDir,
        stdio: "inherit",
        env: process.env,
    });

    frontendProcess.on("error", (error) => {
        console.error(`[watch:frontend] failed to start: ${error.message}`);
        shutdown(1);
    });

    frontendProcess.on("exit", (code) => {
        frontendProcess = null;
        if (shuttingDown) {
            return;
        }

        console.error(`[watch:frontend] exited with code ${code ?? "unknown"}`);
        shutdown(code ?? 1);
    });
}

function startBackendWatcher() {
    if (!existsSync(path.join(svcDir, "pyproject.toml"))) {
        console.error(`[watch] missing ${path.join(svcDir, "pyproject.toml")}`);
        shutdown(1);
        return;
    }

    backendSnapshot = createBackendSnapshot();
    console.log("[watch:backend] watching svc/*.py changes and re-running pytest");
    runBackendTests("initial run");

    backendPollingTimer = setInterval(() => {
        if (shuttingDown) {
            return;
        }

        const nextSnapshot = createBackendSnapshot();
        if (snapshotsDiffer(backendSnapshot, nextSnapshot)) {
            backendSnapshot = nextSnapshot;
            scheduleBackendRun("source change");
        }
    }, 1200);
}

function scheduleBackendRun(reason) {
    if (backendRunInProgress) {
        backendRunQueued = true;
        return;
    }

    runBackendTests(reason);
}

function runBackendTests(reason) {
    backendRunInProgress = true;
    console.log(`[watch:backend] running pytest (${reason})`);

    backendProcess = spawn(uvCommand, ["run", "pytest", "-q"], {
        cwd: svcDir,
        stdio: "inherit",
        env: process.env,
    });

    backendProcess.on("error", (error) => {
        console.error(`[watch:backend] failed to start: ${error.message}`);
        shutdown(1);
    });

    backendProcess.on("exit", (code) => {
        backendProcess = null;
        backendRunInProgress = false;
        if (shuttingDown) {
            return;
        }

        const stamp = new Date().toLocaleTimeString();
        if (code === 0) {
            console.log(`[watch:backend] ${stamp} no test errors`);
        } else {
            console.log(`[watch:backend] ${stamp} errors found (exit ${code ?? "unknown"})`);
        }

        if (backendRunQueued) {
            backendRunQueued = false;
            runBackendTests("queued source change");
        }
    });
}

function createBackendSnapshot() {
    const snapshot = new Map();
    const watchDirs = ["app", "tests"];
    const watchFiles = ["main.py", "pyproject.toml", "requirements.txt"];
    const watchExt = new Set([".py", ".toml"]);

    for (const file of watchFiles) {
        const filePath = path.join(svcDir, file);
        if (existsSync(filePath)) {
            snapshot.set(filePath, statSync(filePath).mtimeMs);
        }
    }

    for (const dir of watchDirs) {
        const dirPath = path.join(svcDir, dir);
        if (!existsSync(dirPath)) {
            continue;
        }

        walkDirectory(dirPath, snapshot, watchExt);
    }

    return snapshot;
}

function walkDirectory(directory, snapshot, watchExt) {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
        const entryPath = path.join(directory, entry.name);
        if (entry.isDirectory()) {
            if (entry.name === "__pycache__" || entry.name === ".venv") {
                continue;
            }

            walkDirectory(entryPath, snapshot, watchExt);
            continue;
        }

        const ext = path.extname(entry.name).toLowerCase();
        if (watchExt.has(ext)) {
            snapshot.set(entryPath, statSync(entryPath).mtimeMs);
        }
    }
}

function snapshotsDiffer(previous, current) {
    if (previous.size !== current.size) {
        return true;
    }

    for (const [file, mtime] of current.entries()) {
        if (!previous.has(file) || previous.get(file) !== mtime) {
            return true;
        }
    }

    return false;
}

function shutdown(exitCode = 0) {
    if (shuttingDown) {
        return;
    }

    shuttingDown = true;
    if (backendPollingTimer) {
        clearInterval(backendPollingTimer);
        backendPollingTimer = null;
    }

    for (const child of [backendProcess, frontendProcess]) {
        if (!child) {
            continue;
        }

        try {
            child.kill("SIGTERM");
        } catch {
            // Ignore shutdown errors from already-finished children.
        }
    }

    setTimeout(() => process.exit(exitCode), 80);
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));
