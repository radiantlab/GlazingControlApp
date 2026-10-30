# Inherited-Codebase Audit

- **Audited commit:** `bf5a278` on `main` (2026-10-29)
- **Period:** fall 2026, weeks 1 to 5
- **Codebase:** the DIAL Control Center, built by Team 76 from 2025-10-11 to
  2026-06-01, then hardened by Alexander Ulbrich from 2026-03-18 to 2026-10-08
  (PRs #49 to #58). The current team's first commit is from 2026-10-09.

This audit records what the current team inherited and what it will change
first. Findings that the code depends on are also recorded where the next
person looks; the last section lists where each one went.

## 1. What Runs and How

| Part | How it runs | State at the audited commit |
| :--- | :--- | :--- |
| FastAPI service (`svc/`) | `uv run python main.py` natively, or the combined Docker image | Runs. Starts in development with the panel and sensor simulators and needs no hardware. |
| React HMI (`web/`) | `npm run dev` (Vite) in development; served by the service from the built image in production | Runs. Builds with `npm run build`. |
| Panel control in production | `HalioAdapter` (`svc/app/adapter.py`) calls the Halio v3 API on the Halio network | Runs, with known faults (section 4). |
| EKO C-BOX and JETI LiVal capture | Polled by the container (Modbus TCP and a mounted capture file) | Runs; the EKO has no staleness check. |
| T-10A and serial JETI | Windows Sensor Agent (`svc/scripts/sensor_agent.py`) posting to `POST /sensors/ingest` | Runs when started by hand. Does not start under Task Scheduler (#95). |
| Database backups | `svc/app/db_backup.py`, when `SVC_DB_BACKUP_INTERVAL_HOURS` > 0 | Code exists and is tested; not yet confirmed on the trailer, and no backup has been restored there. |
| Routines | User-written Python run as a subprocess by `svc/app/routines/manager.py` | Runs; has no tests. |
| Lifecycle script | `scripts/Invoke-ControlCenter.ps1` (start, stop, status, health) | Merged in #97; operator docs and CI do not use it yet (#96). |
| Production stack | Linux container on the Windows trailer PC | Runs under Podman today; the docs mix Podman and Docker (RFC-0007, #86). |

What does not run, or is not confirmed:

- Glazing tint behaves as on/off instead of across 0 to 100, and some tint
  requests to Halio are lost without an error. The cause (app, adapter, or
  Halio) is unknown.
- No restore of a production backup has been tried.
- There is no durable record of sensor dropouts; a dropout leaves a gap rather
  than a recorded failure.
- One-click startup for operators does not exist yet (epic #75).

## 2. Tests and CI

Results at the audited commit:

| Suite | Command | Result |
| :--- | :--- | :--- |
| Backend (pytest, 22 test files) | `uv run pytest tests` in `svc/` | 169 passed |
| Frontend (Vitest, 6 test files) | `npm run test` in `web/` | 26 passed |
| Sensor scripts (Pester 3.4.0) | `Invoke-Pester -Path scripts/sensors/tests` | 10 passed; not run in CI |
| Lifecycle script (Pester 3.4.0) | `Invoke-Pester -Path scripts/tests` | 56 passed; not run in CI |

CI runs on every pull request and on pushes to `main`:

- `ci.yml`: `backend-tests` (pytest with `uv sync --frozen`) and
  `frontend-checks` (Vitest, `tsc`, Vite build).
- `docker-builds.yml`: runtime-version parity, `docker compose config`, and
  image builds.
- `pre-commit` hooks (secret scan, whitespace, flake8) run locally; CI does
  not run them.

Branch protection is ruleset 24736232: no direct pushes to `main`, squash merge
only, and the three jobs above required.

Gaps:

- `HalioAdapter` tests (`svc/tests/test_production.py`) cover listing and
  groups from captured responses, but not setting a tint level or Halio being
  unreachable.
- Routines have no tests.
- No linter runs in CI for the frontend or Python, and neither Pester suite
  runs in CI. PR #91 (issue #59) adds Biome and the sensor Pester suite.
- `CONTRIBUTING.md` said the ruleset required 0 approvals, "raised to 1 when
  the student team joins". The ruleset requires 1 approving review (checked
  2026-10-29), and `CONTRIBUTING.md` now says so.

## 3. Dependencies and Their Age

Dependencies were refreshed to current releases in #57 and #58 (2026-10-08),
so nothing is more than a patch release behind. Runtimes: Python 3.14
(`svc/.python-version`) and Node 24 (`.nvmrc`), pinned the same way in the
`Dockerfile` and checked in CI by `scripts/check-runtime-versions.sh`.

| Area | Pinned | Behind latest on 2026-10-29 |
| :--- | :--- | :--- |
| Python service | FastAPI 0.162.0, uvicorn 0.54.0, pydantic 2.14.1, pymodbus 3.16.1, pyserial 3.5, numpy 2.5.4, scipy 1.18.1, colour-science 0.4.7 | pydantic 2.14.2, tzdata 2026.6 |
| Python dev | pytest 9.1.1, httpx2 2.16.0 | pytest 9.2.0 |
| Web | React 19.3.0, react-router-dom 7.18.4, recharts 3.10.1 | React 19.3.1, react-router-dom 7.18.5 |
| Web dev | TypeScript 7.0.2, Vite 8.3.4, Vitest 5.0.3, jsdom 30.1.2 | Vite 8.3.5, Vitest 5.0.5 |

`uv.lock` is the only exact Python pin (ADR 0003). Dependabot opens weekly
updates for GitHub Actions, npm, uv, and Docker base images. `pyserial` 3.5 is
the latest release, but that release dates from 2020; it is the one
dependency with no recent maintenance.

## 4. Open Risks and Known Debt

Risks are ranked and owned in [`docs/risks.md`](./risks.md). The debt found
here:

- **Lost and binary tint commands.** See section 1. This is the most serious
  control fault.
- **Backups unproven.** The code is tested, but no one has restored a
  production backup (requirements item 1; #83 for bootstrapping a new
  `audit.db`).
- **No dropout record.** The EKO has no staleness check, and only
  agent-fed devices report stale.
- **Two container runtimes in the docs.** Podman on the trailer, Docker in CI
  (RFC-0007, #86).
- **Large files.** `svc/app/state.py` (1,325 lines), `svc/app/routes.py`
  (761), `web/src/AppHMI.tsx` (1,380), and `web/src/components/LogsPanel.tsx`
  (1,274) mix several concerns and are where most changes land.
- **Routines run arbitrary Python** from the HMI as subprocesses. This is
  acceptable only because the service is LAN-only (ADR 0005); it has no tests.
- **Biome warnings.** 174 warnings across 11 rules in `web/` (#92).
- **Sensor metric names.** Each driver chose its own names and units
  (RFC-0006).

## 5. Predecessor Handoff and Retrospective

The repository holds no handoff document or retrospective from Team 76. What
the team inherited in the repository:

- `README.md`, `OVERVIEW.md`, `DEV-SETUP.md`, and the guides in `docs/`, which
  were corrected against the code in #51.
- ADRs 0001 to 0005, written during the 2026 hardening (#49 to #58).

**TODO(team):** name where Team 76's handoff document and project
retrospective are kept (or record that none was written), and summarize the
forward-looking section of the retrospective here.

## 6. Upstream Contribution Rules

There is no upstream project: the repository is `radiantlab/GlazingControlApp`
and the team commits to it directly through pull requests. The vendor systems
the code talks to (the Halio v3 API, the EKO C-BOX, the JETI and Konica Minolta
instruments) are used through their documented interfaces only; the team does
not bypass vendor software without the partner confirming it keeps calibration
(`AGENTS.md`).

## 7. What We Will Change First

In priority order, from `docs/requirements.md`:

1. **Protect research data.** Confirm backups on the trailer and restore one;
   confirm every instrument reaches `audit.db`; record dropouts as failures.
2. **Fix glazing control.** Find why tint is binary and why requests are
   lost, with tests for Halio being unreachable.
3. **One-click startup** for operators (epic #75), using the lifecycle script.
4. **One container runtime** (RFC-0007, #86).
5. **CI coverage:** Biome and both Pester suites in CI (#59, #91, #96).

## Where the Findings Went

| Finding | Recorded in |
| :--- | :--- |
| Halio is LAN-only and unauthenticated; the trailer PC runs Windows; Linux containers cannot open COM ports | Constraints in `docs/requirements.md`; ADRs 0002 and 0005 |
| Production and development data never mix | ADR 0004; `AGENTS.md` |
| Run Pester under Windows PowerShell 5.1 with Pester 3.4.0 | `CONTRIBUTING.md` |
| Keep or replace the container runtime | RFC-0007 |
| Sensor metric names and units | RFC-0006 |
| Ranked risks and owners | `docs/risks.md` |
