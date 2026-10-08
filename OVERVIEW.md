# Project overview

DIAL Control Center combines a FastAPI service and React HMI for controlling
Halio electrochromic glazing, collecting sensor data, and running study
routines.

## Runtime architecture

- `svc/app/config.py` validates `SVC_ENVIRONMENT`, runtime/config paths, dwell
  settings, and required production Halio credentials.
- `svc/app/service.py` selects the development simulator or production
  `HalioAdapter`.
- `svc/app/state.py` stores audits, mutable panel state, groups, sensor data,
  and routines in the environment database.
- `svc/app/sensors/manager.py` validates environment-specific sensor config and
  constructs simulated or physical clients.
- `svc/app/routines/manager.py` stores generated scripts beneath the selected
  runtime directory.
- `svc/app/routes.py` exposes control, health, logs, sensors, metrics, and
  routine APIs.

## Environment layout

```text
svc/config/development/       tracked safe development configuration
svc/config/production.example tracked production template
svc/.runtime/development/     ignored local development runtime
svc/data/                     preserved production-compatible host data
```

Production configuration lives outside version control and is mounted
read-only. Production data remains mounted at `/app/svc/data`, preserving the
existing `/app/svc/data/audit.db` path.

## Deployment files

- `docker-compose.development.yml` uses simulated defaults and a named data
  volume.
- `docker-compose.yml` is production-only and requires explicit absolute data,
  config, and backup host paths plus Halio credentials.
- `scripts/production_preflight.py` verifies and backs up the existing
  production database before upgrade.

## Web application

- `web/src/api.ts` is the typed API client.
- `web/src/AppHMI.tsx` is the primary control and monitoring screen.
- `web/src/mockData.ts` supplies a browser-only fallback when the backend is
  unavailable.
- Components under `web/src/components` provide room control, logs, routines,
  documentation, and sensor visualization.

## Public environment contract

`GET /health` reports `environment`, `control_source`, and `sensor_source`.
Group mutation APIs are development-only. Generic routine execution `mode`
values (`once` and `interval`) are unrelated to deployment environments.

See [DEV-SETUP.md](./DEV-SETUP.md) for local and production procedures.
