# Contributing Guide

How to set up, test, review, and merge contributions to DIAL Control Center.

## The Pipeline

All code changes follow a strict pipeline:

1. **Issue**: Every change starts from an issue describing the problem or desired enhancement.
2. **Branch**: Create a short-lived branch off `main` using one of the accepted branch prefixes:
   - `feat/` — new feature
   - `fix/` — bug fix
   - `docs/` — documentation only
   - `chore/` — maintenance, dependencies, tooling
   - `ci/` — CI/CD workflow changes
   - `refactor/` — code restructuring without behavior changes
3. **Commits**: Follow Conventional Commits format for commit subjects (e.g. `feat(sensors): add T-10A auto-discovery`, `fix(routes): enforce dwell time on group tint`).
4. **Pull Request**: Open a PR against `main`. All CI status check gates must pass.
5. **Review & Merge**: 0 approvals now; raised to 1 when the student team joins. Merged to `main` exclusively via **squash merge** (no merge commits, no rebase merges).

## Quality Gates & Ruleset 24736232

Branch protection is enforced on `main` via GitHub **Ruleset 24736232**. Direct pushes and branch deletions are disabled. All PRs must satisfy the following gates:

| Gate / Rule | Enforced By | Details |
| :--- | :--- | :--- |
| **Backend Tests** | CI job `backend-tests` | Runs `uv run pytest tests/ -v` on Python (`svc/.python-version`) with dependencies frozen from `uv.lock`. |
| **Frontend Checks** | CI job `frontend-checks` | Runs `npm run test` (Vitest), `npm run typecheck` (`tsc`), and `npm run build` on Node (`.nvmrc`). |
| **Docker & Version Checks** | CI job `docker-builds` | Runs `scripts/check-runtime-versions.sh`, validates `docker compose config --quiet`, and builds the combined image. |
| **Runtime Version Parity** | `docker-builds` & scripts | `Dockerfile` base images must match `svc/.python-version` and `.nvmrc`, and the uv image must match `.github/workflows/ci.yml`. |
| **Python Dependency Pinning** | `backend-tests` | `uv.lock` is the only exact Python pin. Dependencies are synced with `uv sync --frozen`. |
| **Approving Reviews** | Ruleset 24736232 | 0 approvals now; raised to 1 when the student team joins. |
| **Merge Method** | Ruleset 24736232 | Squash merge only. |

## Exact Local Commands

Run these checks locally before opening or updating a PR.

### 1. Pre-commit Hooks (Linting & Secrets)
```bash
uv tool install pre-commit
pre-commit install
pre-commit run --all-files
```

### 2. Backend Validation (from `svc/`)
```bash
cd svc
uv sync --frozen
uv run pytest tests/ -v
```

### 3. Frontend Validation (from `web/`)
```bash
cd web
npm ci
npm run test
npm run typecheck
npm run build
```

### 4. Runtime & Container Checks (from repository root)
```bash
# Verify Dockerfile matches runtime versions
./scripts/check-runtime-versions.sh

# Validate compose configuration
docker compose config --quiet

# Build Docker image
docker build -t glazing-control-app:local .
```

## Runtime Versions and Dependency Management

- **Python Pinning**: `svc/uv.lock` is the only exact Python pin. `pyproject.toml` defines abstract dependencies. Never edit `uv.lock` by hand; update dependencies using `uv add` or `uv lock --upgrade`.
- **Node Pinning**: `web/package-lock.json` pins frontend dependencies. Always install with `npm ci`.
- **Runtime Parity**: When updating `svc/.python-version`, `.nvmrc`, or the uv setup action version in `.github/workflows/ci.yml`, the corresponding `FROM` or `COPY` stages in `Dockerfile` must be updated as well. Enforced by `scripts/check-runtime-versions.sh`.

## Issues and Labels

Work is tracked in GitHub Issues. When filing or triaging work, use the issue forms and apply the appropriate labels:

- `bug` — something isn't working
- `enhancement` — new feature or behavioral improvement
- `documentation` — documentation additions or updates
- `chore` — maintenance, dependencies, and tooling
- `hardware` — physical trailer instruments (Halio, T-10A, JETI, EKO C-BOX)
- `ready-for-agent` — task well-specified for AI agent execution
- `ready-for-human` — requires human testing, physical hardware, or partner discussion
- `needs-triage` — new issue awaiting review and categorization
- `dependencies` — dependency updates
