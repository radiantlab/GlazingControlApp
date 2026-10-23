# Project AI and Agent Guidance

These instructions apply to AI-assisted work throughout this repository. Read
[`CONTRIBUTING.md`](./CONTRIBUTING.md) and [`DEV-SETUP.md`](./DEV-SETUP.md)
for contribution and setup steps.

## Project Context

- This is the inherited DIAL Control Center for OSU's mobile daylighting
  research trailer; improve the existing system rather than replacing it
  without evidence.
- The stack is a Python 3.14 (`svc/.python-version`) FastAPI service,
  React/TypeScript web client (Node 24, `.nvmrc`), SQLite, and Docker/Podman.
  The trailer computer runs Windows.
- The system is local-first and must keep core functions available when
  instruments are missing or unreachable; report instrument status and failures
  instead of treating missing readings as valid data or crashing startup.
- Hardware integrations are vendor- and configuration-specific. Prefer the
  existing simulator for development; do not assume access to trailer hardware.
- Sensor data, studies, glazing control, and scheduling are parts of a research
  system where reliable records and clear failure states matter.

## Repository Layout

- `svc/`: FastAPI service. `app/` holds routes, models, config, the panel
  simulator and `HalioAdapter`, `sensors/` (clients, simulators, manager,
  ingestion) and `routines/`; `tests/` is the pytest suite; `config/` holds
  development config and the `production.example` template;
  `scripts/sensor_agent.py` is the Windows Sensor Agent.
- `web/`: React/TypeScript client built with Vite; tests use Vitest.
- `scripts/`: repo-level tooling (`check-runtime-versions.sh`, production
  preflight) and `sensors/` PowerShell scripts, including
  `Start-SensorAgent.ps1`.
- `docs/`: architecture, sensor and Halio setup, and hardware references.
- `.github/`: CI workflows (`ci.yml`, `docker-builds.yml`), Dependabot, PR
  template, and issue forms.
- Root: `Dockerfile`, `docker-compose.yml` (production),
  `docker-compose.development.yml`, `.pre-commit-config.yaml`.

## Non-Negotiable Constraints

- Do not change the application's API: do not add, remove, rename, or alter
  routes, methods, request/response schemas, status-code behavior, or public
  data contracts.
- If a requested change appears to require an API change, stop and explain the
  conflict instead of making the change.
- Never create, amend, or run a command that creates a Git commit. Do not stage
  changes; leave the diff for a human to inspect and commit.
- Never work on, commit to, or push to `main`. Work on a short-lived branch
  named with a prefix from `CONTRIBUTING.md`.
- `SVC_ENVIRONMENT=production` talks to the live trailer, Halio, and physical
  sensors. Never set it for tests or local runs. `svc/tests/conftest.py` pins
  `development`; configuration tests may set `production` only with
  `monkeypatch`, `tmp_path` directories, and placeholder Halio values to check
  `Settings.from_env()` validation.
- AI-generated Python code must follow PEP 8. For TypeScript and other
  languages, follow the repository's existing conventions and type safety.
- Do not replace the existing architecture or remove working behavior without
  evidence and explicit direction.

## Architecture and Change Practices

- Keep the React client, FastAPI service, service abstractions, simulator, and
  hardware adapters consistent with their existing boundaries.
- Preserve simulator operation and existing behavior when modifying hardware
  integrations; test failure and disconnected-device paths.
- Do not bypass vendor software or directly interface with hardware unless the
  partner has confirmed that doing so preserves calibration and accuracy.
- Store application data through the backend and its existing persistence
  patterns, not browser local storage.
- Make the smallest complete change, handle errors visibly, and update directly
  affected docs and tests.
- Sensor acquisition is split between two processes. The Linux container reads
  network and file sensors itself: the EKO C-BOX over Modbus TCP and the JETI
  LiVal capture file. It cannot open Windows COM ports, so devices marked
  `"acquisition": "external"` in `sensors_config.json` (T-10A, and JETI with
  `transport: "serial_scpi"`) are read by the native Windows Sensor Agent,
  which posts to `POST /sensors/ingest`. The container registers external
  devices but never opens them. See `docs/production_sensor_setup.md`.

## Testing and Style

- Before handing back a change, run the checks it touches, as listed under
  "Exact Local Commands" in `CONTRIBUTING.md`:
  - Hooks: from the repository root, run `pre-commit run --all-files`.
  - Backend tests: from `svc`, run `uv run pytest tests/ -v`.
  - Frontend tests: from `web`, run `npm ci` when dependencies are absent,
    then `npm run test`, `npm run typecheck`, and `npm run build`.
  - Runtime, Dockerfile, or Compose changes: run
    `./scripts/check-runtime-versions.sh` and the container checks.
- CI is defined in `.github/workflows/ci.yml` (`backend-tests`,
  `frontend-checks`) and `.github/workflows/docker-builds.yml`
  (`docker-builds`); keep local validation consistent with those jobs.
- The docs are long. Search them with `grep` or `rg` for the term you need
  and read only the matching sections, rather than reading whole files.
- Add or update tests for changed behavior, including relevant failure cases.
- Do not claim a test, hardware check, or validation passed unless it was run.

## AI Use and Confidentiality

- Use only AI tools explicitly approved by both the team and project partner.
- No approved-tool list or partner data classification is recorded in this
  repository; until the team documents them, use AI only with public material
  and project code explicitly cleared for that tool.
- Never submit credentials, API keys, Wi-Fi/VPN details, private network
  configuration, raw or identifiable sensor data, private partner documents,
  or unpublished vendor material to an AI tool.
- Never put secrets or site-specific credentials in source, examples, logs,
  prompts, issues, or pull requests; use ignored local configuration instead.
- `.claude/settings.json` denies agent reads of the files that hold this
  material: `.env` and `.env.production` files, `svc/config/production/`,
  production databases and backups, sensor captures and logs, and the
  ignored API documents `docs/TintSpecifics*`. The `.example` templates stay
  readable. The rules cover Claude Code's file tools and simple shell reads
  such as `cat`, but not recursive searches or scripts that open files
  themselves, so they back up this rule rather than replace it.
- If data classification or tool approval is unclear, do not share the material;
  ask the team's AI Coordinator and project partner first.

## Context to Confirm and Maintain

- The current team must name its AI Coordinator and confirm the approved AI
  tools and data boundary with the partner; the AI Coordinator owns recording
  that decision here or in the team's approved policy.
- The current team must verify API contracts, hardware configuration, and
  sensor-data handling against maintained project documentation before changing
  related code; the maintainer of the affected subsystem owns those updates.
- Do not infer current team roles or approvals from contributors listed in the
  inherited README or from informal meeting notes.
