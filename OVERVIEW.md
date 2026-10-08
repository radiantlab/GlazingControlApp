# Project overview

DIAL Control Center combines a FastAPI service and React HMI for controlling
Halio electrochromic glazing, collecting sensor data, and running study
routines.

## Runtime architecture

- `svc/app/config.py` validates `SVC_ENVIRONMENT`, runtime/config paths, dwell
  settings, and the required production Halio URL and site ID.
- `svc/app/service.py` selects the development simulator or production
  `HalioAdapter`.
- `svc/app/adapter.py` is the `HalioAdapter`: it maps Halio v3 windows and
  groups to panels and groups, and creates missing single-window groups on the
  controller.
- `svc/app/simulator.py` is the development panel simulator.
- `svc/app/state.py` stores audits, mutable panel state, groups, sensor data,
  and routines in the environment database.
- `svc/app/sensors/manager.py` validates environment-specific sensor config and
  constructs simulated or physical clients. In production the container polls
  the EKO C-BOX and the mounted LiVal capture itself; devices marked
  `"acquisition": "external"` (COM-port T-10A and JETI serial) are read by the
  native Windows Sensor Agent (`svc/scripts/sensor_agent.py`), which posts to
  `POST /sensors/ingest`.
- `svc/app/sensors/host_agent.py` is the agent's collection and durable
  delivery outbox; it never opens `audit.db`.
- `svc/app/sensors/ingestion.py` converts sensor readings into ingestion
  events.
- `svc/app/sensors/serial_discovery.py` lists serial ports and matches
  `port_identity` selectors without opening ports.
- `svc/app/db_backup.py` writes periodic SQLite backups to
  `SVC_DB_BACKUP_DIR`.
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
  config, and backup host paths (`SVC_PRODUCTION_DATA_DIR`,
  `SVC_PRODUCTION_CONFIG_DIR`, `SVC_DB_BACKUP_DIR`), the LiVal capture file
  (`SVC_JETI_CAPTURE_PATH`), plus `HALIO_API_URL` and `HALIO_SITE_ID`.
- `scripts/production_preflight.py` verifies and backs up the existing
  production database before upgrade.
- `svc/scripts/sensor_agent.py` is the Windows Sensor Agent CLI
  (`list-ports`, `once`, `continuous`).
- `scripts/sensors/` holds the PowerShell entry point for the agent
  (`Start-SensorAgent.ps1`) and the sensor capture and backup scripts. See
  [scripts/sensors/README.md](./scripts/sensors/README.md).

## Web application

- `web/src/main-hmi.tsx` is the frontend entry loaded by `web/index.html`. It
  sets up the router (`/`, `/docs`, `/docs/routines`, `/docs/sensors`) and the
  toast provider.
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

## Naming

The product is DIAL Control Center. Package, image, container, and volume names
(`glazing-control-service`, `glazing-web`, `glazing-control-app`,
`glazing-development-data`, and others) keep the old `glazing-*` prefix on
purpose so existing deployments, scripts, and volumes keep working.

See [DEV-SETUP.md](./DEV-SETUP.md) for local and production procedures.
