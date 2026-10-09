# Project AI and Agent Guidance

These instructions apply to AI-assisted work throughout this repository. Read
[`CONTRIBUTING.md`](./CONTRIBUTING.md) and [`DEV-SETUP.md`](./DEV-SETUP.md)
for contribution and setup steps.

## Project Context

- This is the inherited DIAL Control Center for OSU's mobile daylighting
  research trailer; improve the existing system rather than replacing it
  without evidence.
- The stack is a Python 3.11–3.13 FastAPI service, React/TypeScript web client,
  SQLite, and Docker/Podman. The trailer computer runs Windows.
- The system is local-first and must keep core functions available when
  instruments are missing or unreachable; report instrument status and failures
  instead of treating missing readings as valid data or crashing startup.
- Hardware integrations are vendor- and configuration-specific. Prefer the
  existing simulator for development; do not assume access to trailer hardware.
- Sensor data, studies, glazing control, and scheduling are parts of a research
  system where reliable records and clear failure states matter.

## Non-Negotiable Constraints

- Do not change the application's API: do not add, remove, rename, or alter
  routes, methods, request/response schemas, status-code behavior, or public
  data contracts.
- If a requested change appears to require an API change, stop and explain the
  conflict instead of making the change.
- Never create, amend, or run a command that creates a Git commit. Do not stage
  changes; leave the diff for a human to inspect and commit.
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

## Testing and Style

- Backend tests: from `svc`, run `uv run pytest tests/ -v`.
- Frontend tests: from `web`, run `npm ci` when dependencies are absent, then
  `npm run test`, `npm run typecheck`, and `npm run build`.
- CI is defined in `.github/workflows/ci.yml`; keep local validation consistent
  with its backend and frontend jobs.
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
