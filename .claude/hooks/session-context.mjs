/**
 * SessionStart: the facts every session would otherwise have to be told,
 * printed into context. Branch and whether it is main, uncommitted changes,
 * the Node and uv in use against `.nvmrc` and `svc/.python-version`, and
 * whether `SVC_ENVIRONMENT` points at the live trailer. Local checks only, no
 * network, so it never delays a session for long.
 *
 * Adapted from adulbrich/eecs-capstone (.claude/hooks/session-context.mjs),
 * MIT License, Copyright (c) 2026 Alex Ulbrich. The compose probe is left
 * out: production Compose here fails without its required variables, and the
 * trailer may run Podman, so the answer would often be wrong.
 */
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { cleanEnv, currentBranch, git, readInput, repoRoot } from "./lib.mjs";

/** The trimmed contents of a file, or "" if it cannot be read. */
function readVersion(path) {
  try {
    return readFileSync(path, "utf8").trim();
  } catch {
    return "";
  }
}

/** `uv --version`, or "" if uv is not on PATH or does not answer quickly. */
function uvVersion() {
  try {
    return execFileSync("uv", ["--version"], {
      encoding: "utf8",
      env: cleanEnv,
      stdio: ["ignore", "pipe", "ignore"],
      timeout: 3000,
    }).trim();
  } catch {
    return "";
  }
}

const input = readInput();
const cwd = input.cwd ?? process.cwd();
const root = repoRoot(cwd);
const lines = [];

const branch = currentBranch(cwd) || "(detached)";
lines.push(
  branch === "main"
    ? "Branch: main. Do not work here (AGENTS.md): pull with `git pull --ff-only`, then create a branch with a CONTRIBUTING.md prefix before editing."
    : `Branch: ${branch}.`
);

const dirty = git(cwd, ["status", "--porcelain"])
  .split("\n")
  .filter(Boolean).length;
lines.push(
  dirty === 0
    ? "Working tree: clean."
    : `Working tree: ${dirty} uncommitted path(s). They may be someone else's work in progress; do not discard them.`
);

const wantedNode = readVersion(join(root, ".nvmrc")).replace(/^v/, "");
const node = process.version.replace(/^v/, "");
lines.push(
  wantedNode && node.split(".")[0] !== wantedNode.split(".")[0]
    ? `Node: ${node} on PATH, but .nvmrc wants ${wantedNode}. Frontend checks should run on the .nvmrc version.`
    : `Node: ${node}.`
);

const wantedPython = readVersion(join(root, "svc", ".python-version"));
const uv = uvVersion();
lines.push(
  uv
    ? `Python: ${wantedPython || "unknown"} from svc/.python-version, installed by ${uv}.`
    : "uv: not found on PATH. Backend commands (`uv sync --frozen`, `uv run pytest`) need it; see DEV-SETUP.md."
);

const environment = (process.env.SVC_ENVIRONMENT ?? "").trim().toLowerCase();
if (environment === "production") {
  lines.push(
    "WARNING: SVC_ENVIRONMENT=production is set in this shell. Production talks to the live trailer, Halio, and physical sensors. Do not run tests or the service from this shell (AGENTS.md)."
  );
} else if (environment) {
  lines.push(`SVC_ENVIRONMENT: ${environment}.`);
}

lines.push(
  "Rules: agents do not stage or commit (enforced by .claude/hooks/guard-git.mjs). Checks to run are in CONTRIBUTING.md, \"Exact Local Commands\"."
);

process.stdout.write(`${lines.join("\n")}\n`);
