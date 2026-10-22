# Contributing Guide

How to set up, test, review, and merge contributions to DIAL Control Center so they meet our Definition of Done.

For environment setup (prerequisites, `.env` files, running the service and web client), see [`DEV-SETUP.md`](./DEV-SETUP.md). AI-assisted work must also follow [`AGENTS.md`](./AGENTS.md).

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

## Definition of Done

A contribution is done when all of the following are true:

- It is linked to an issue, and the PR description says what changed and why.
- All CI gates below are green.
- Changed behavior has new or updated tests, including at least one failure or error case.
- The local commands below were run, and the PR names which ones.
- Pre-commit hooks pass with no new findings.
- Docs affected by the change (README, `DEV-SETUP.md`, this guide) are updated.
- No secrets, credentials, or raw sensor data are committed (see [Secrets and Data](#secrets-and-data)).
- It is reviewed per [Contribution Norms](#contribution-norms) and squash-merged to `main`.

## Quality Gates

Branch protection is enforced on `main` via GitHub **Ruleset 24736232**. Direct pushes and branch deletions are disabled. All PRs must satisfy the following gates:

| Gate / Rule | Enforced By | Details |
| :--- | :--- | :--- |
| **Backend Tests** | `backend-tests` job (`.github/workflows/ci.yml`) | Runs `uv run pytest tests/ -v` on Python (`svc/.python-version`) with dependencies frozen from `uv.lock`. |
| **Frontend Checks** | `frontend-checks` job (`.github/workflows/ci.yml`) | Runs `npm run test` (Vitest), `npm run typecheck` (`tsc`), and `npm run build` on Node (`.nvmrc`). |
| **Docker & Version Checks** | `docker-builds` job (`.github/workflows/docker-builds.yml`) | Runs `scripts/check-runtime-versions.sh`, validates `docker compose config --quiet`, and builds the combined image and compose services. |
| **Runtime Version Parity** | `scripts/check-runtime-versions.sh` (in `docker-builds`) | `Dockerfile` base images must match `svc/.python-version` and `.nvmrc`, and the uv image must match the uv version pinned in `.github/workflows/ci.yml`. |
| **Python Dependency Pinning** | `backend-tests` | `uv.lock` is the only exact Python pin. Dependencies are synced with `uv sync --frozen`. |
| **Approving Reviews** | Ruleset 24736232 | 0 approvals now; raised to 1 when the student team joins. |
| **Merge Method** | Ruleset 24736232 | Squash merge only. |

## Exact Local Commands

Run these checks locally before opening or updating a PR. Each block starts from the repository root.

### 1. Pre-commit Hooks (Linting & Secrets)
```bash
uv tool install pre-commit
pre-commit install
pre-commit run --all-files
```

### 2. Backend Validation
```bash
cd svc
uv sync --frozen
uv run pytest tests/ -v
```

### 3. Frontend Validation
```bash
cd web
npm ci
npm run test
npm run typecheck
npm run build
```

### 4. Runtime & Container Checks
```bash
# Verify Dockerfile matches runtime versions
./scripts/check-runtime-versions.sh

# Validate compose configuration. Production Compose requires these
# variables; placeholders are enough because config never opens the paths
# or contacts Halio (the same values CI uses).
SVC_PRODUCTION_DATA_DIR=/tmp/glazing-ci/data \
SVC_PRODUCTION_CONFIG_DIR=/tmp/glazing-ci/config \
SVC_DB_BACKUP_DIR=/tmp/glazing-ci/db-backups \
SVC_JETI_CAPTURE_PATH=/tmp/glazing-ci/specbos-lival.capture \
HALIO_API_URL=http://halio.invalid:8083/api/v3 \
HALIO_SITE_ID=ci-placeholder \
docker compose config --quiet

# Build Docker image
docker build -t glazing-control-app:local .
```

## Runtime Versions and Dependency Management

- **Python Pinning**: `svc/uv.lock` is the only exact Python pin. `pyproject.toml` defines abstract dependencies. Never edit `uv.lock` by hand; update dependencies using `uv add` or `uv lock --upgrade`.
- **Node Pinning**: `web/package-lock.json` pins frontend dependencies. Always install with `npm ci`.
- **Runtime Parity**: When updating `svc/.python-version`, `.nvmrc`, or the uv `version:` pinned in the `setup-uv` step of `.github/workflows/ci.yml`, update the matching `FROM` or `COPY --from` line in `Dockerfile` as well. Enforced by `scripts/check-runtime-versions.sh`.

## Contribution Norms

Each team member owns one piece of accepted work per sprint.

- Claim an issue on the repo (or create one that reflects what your change addresses).
- Pull requests must be reviewed by at least one other team member. This is a team norm today; Ruleset 24736232 will enforce it once the approval requirement is raised to 1.

## Secrets and Data

- Never commit secrets, API keys, or site-specific credentials. Use the git-ignored `.env` files described in `DEV-SETUP.md`.
- Secrets and site-specific values (such as `HALIO_SITE_ID`) live in the private [`radiantlab/DIAL-Internal-Documentation`](https://github.com/radiantlab/DIAL-Internal-Documentation) repository. Request access from the project partner, and copy values from there into your ignored `.env` files rather than into this repository.
- Do not paste credentials, private network details, or raw sensor data into issues, PRs, or logs.
- The `detect-secrets` pre-commit hook catches some mistakes, not all of them; review your diff before pushing.
- Reviewed false positives (the Halio `hardwareId` values in the test fixtures) are recorded in `.secrets.baseline`. If the hook flags a value that is not a secret, update the baseline with `detect-secrets scan --baseline .secrets.baseline`, mark the finding with `detect-secrets audit .secrets.baseline`, and say so in the PR.
- Report security problems privately to the team lead and project partner, not in a public issue.

## Issues and Labels

Work is tracked in GitHub Issues. File new work with the **Bug report** or **Enhancement** issue form; both apply `needs-triage` automatically. When triaging, apply the appropriate labels:

- `bug` — something isn't working
- `enhancement` — new feature or behavioral improvement
- `documentation` — documentation additions or updates
- `hardware` — physical trailer instruments (Halio, T-10A, JETI, EKO C-BOX)
- `needs-triage` — new issue awaiting review and categorization
- `ready-for-agent` — task well-specified for AI agent execution
- `ready-for-human` — requires human testing, physical hardware, or partner discussion
- `epic` — tracks a group of related issues
- `good first issue` — good for newcomers
- `help wanted` — extra attention is needed
- `question` — further information is requested
- `duplicate`, `invalid`, `wontfix` — triage outcomes

Dependabot applies these to its own pull requests: `dependencies`, `docker`, `github_actions`, `python:uv`, `javascript`.
