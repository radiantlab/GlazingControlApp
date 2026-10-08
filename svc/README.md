# Control service

FastAPI service for Halio glazing control, sensor collection, routines, and
audit logging.

## Environments

`SVC_ENVIRONMENT` is required:

- `development`: simulated panel backend and simulated sensors by default.
- `production`: Halio panel backend and physical sensors only.

Legacy `SVC_MODE`, `sim`, and `real` environment values are rejected.

## Local development

```powershell
Copy-Item .env.example .env
uv sync
uv run python main.py
```

Development reads `config/development` and writes only to
`.runtime/development`.

## Configuration

This section is the single reference for environment variables. Other docs
should point here rather than restate defaults.

### Service

| Variable | Development default | Production |
|---|---|---|
| `SVC_ENVIRONMENT` | Required | Required |
| `SVC_HOST` | `127.0.0.1` | Compose sets `0.0.0.0` |
| `SVC_PORT` | `8000` | Compose sets `8000` |
| `UVICORN_RELOAD` | `false` | Compose sets `false` |
| `CORS_ORIGINS` | Empty | Empty unless needed |
| `WEB_DIST_DIR` | `<repo>/web/dist` | Dockerfile sets `/app/web/dist` |
| `SVC_DATA_DIR` | `.runtime/development` | Required mounted data directory |
| `SVC_CONFIG_DIR` | `config/development` | Required read-only config directory |
| `SVC_MIN_DWELL_SECONDS` | `20` | `20` unless overridden |
| `SVC_DB_BACKUP_INTERVAL_HOURS` | `0` | Compose default `24` |
| `SVC_DB_BACKUP_DIR` | Disabled | Compose sets `/app/db-backups` |
| `SVC_SENSOR_INPUT_DIR` | `SVC_DATA_DIR` | Compose sets `/app/svc/sensor-input` |
| `SVC_SENSOR_ACQUISITION` | `embedded` | Compose sets `embedded` |
| `SVC_SENSOR_INGEST_TOKEN` | Empty (ingestion disabled) | Required when any device is `"acquisition": "external"` |
| `SVC_DEVELOPMENT_USE_PHYSICAL_T10A` | `false` | Ignored |
| `SVC_DEVELOPMENT_USE_PHYSICAL_JETI` | `false` | Ignored |
| `SVC_DEVELOPMENT_USE_PHYSICAL_EKO` | `false` | Ignored |
| `HALIO_API_URL` | Unused | Required, Halio v3 base URL (`http://<controller>:8083/api/v3`) |
| `HALIO_SITE_ID` | Unused | Required |
| `HALIO_API_KEY` | Unused | Optional; the v3 API does not use it |

`SVC_HOST` defaults to loopback, so a native `uv run python main.py` is not
reachable from other machines on the trailer network unless you set
`SVC_HOST=0.0.0.0`. Both Compose files set it.

`CORS_ORIGINS` is a comma-separated list appended to the built-in origins
(`http://localhost:5173`, `http://127.0.0.1:5173`, `http://localhost`,
`http://127.0.0.1`). The HMI served by the backend is same-origin and needs
none.

When `WEB_DIST_DIR` does not exist the service runs API-only and logs
`Frontend dist directory not found`. Run `npm run build` in `web` to serve the
HMI from a native backend.

Physical-device testing in development is opt-in:

- `SVC_DEVELOPMENT_USE_PHYSICAL_T10A=true`
- `SVC_DEVELOPMENT_USE_PHYSICAL_JETI=true`
- `SVC_DEVELOPMENT_USE_PHYSICAL_EKO=true`

Health reports `sensor_source: mixed` when any override is enabled.

### Halio authentication

The Halio v3 API at `http://<controller>:8083/api/v3` is unauthenticated and
reachable only on the trailer LAN. The legacy key-based API on port 8084 is no
longer served by the controller. Production requires `HALIO_API_URL` and
`HALIO_SITE_ID`. `HALIO_API_KEY` is optional: the adapter sends it as
`X-API-Key` only when it is set.

### Compose host paths

`docker-compose.yml` reads these from `svc/.env.production` to build its bind
mounts. The application never reads them.

| Variable | Purpose |
|---|---|
| `SVC_PRODUCTION_DATA_DIR` | Existing host directory containing `audit.db`, mounted at `/app/svc/data` |
| `SVC_PRODUCTION_CONFIG_DIR` | Host production config directory, mounted read-only at `/app/svc/config` |
| `SVC_DB_BACKUP_DIR` | Host backup directory, mounted at `/app/db-backups` |
| `SVC_JETI_CAPTURE_PATH` | Active LiVal capture file, mounted read-only at `/app/svc/sensor-input/specbos-lival.capture` |

### Windows Sensor Agent

`scripts/sensor_agent.py` loads `svc/.env`, then `svc/.env.production`, and
explicit process variables win over both.

| Variable | Default |
|---|---|
| `SENSOR_AGENT_CONFIG` | Unset. Config lookup order: `SENSOR_AGENT_CONFIG`, then `SVC_PRODUCTION_CONFIG_DIR/sensors_config.json`, then `SENSORS_CONFIG_FILE`, then `SVC_CONFIG_DIR/sensors_config.json` (`config/production`) |
| `SENSOR_AGENT_DATA_DIR` | `SVC_PRODUCTION_DATA_DIR`, then `SVC_DATA_DIR`, then `svc/data` |
| `SENSOR_INGEST_URL` | `http://127.0.0.1:8000/sensors/ingest` |
| `SENSOR_INGEST_TOKEN` | `SVC_SENSOR_INGEST_TOKEN` |
| `SENSOR_AGENT_OUTBOX` | `svc/sensor-agent-data/outbox.db` |
| `SENSOR_AGENT_LOG_FILE` | `svc/sensor-agent-data/agent.log` |
| `SENSOR_AGENT_LOG_LEVEL` | `INFO` |
| `SENSOR_AGENT_ID` | Host name |
| `SENSOR_AGENT_BATCH_SIZE` | `250` |

## Storage

The SQLite database remains named `audit.db` for production compatibility, but
it contains audits, panel state, groups, sensors, readings, spectra, and
routines. Every database and generated routine path is derived from
`SVC_DATA_DIR`.

Production retains `/app/svc/data/audit.db`. Development containers use an
isolated named volume at `/app/svc/data`.

## Sensors

Environment-specific `sensors_config.json` supports:

- `t10a`: Konica Minolta T-10A over serial, simulated in development.
- `jeti_spectraval`: `.cap` watcher or direct SPECFIRM serial; development file transport includes a simulator writer.
- `eko_ms90_plus`: EKO C-BOX over Modbus TCP, simulated in development.

A JETI file entry names its capture with `input_path`. Relative values resolve
beneath `SVC_SENSOR_INPUT_DIR`; the legacy `output_path` key resolves beneath
`SVC_DATA_DIR`. Paths that escape their root are rejected. Production validates
all configured physical ports, hosts, transports, and input paths before
database initialization.

Each device entry accepts `"acquisition": "embedded"` (default) or
`"external"`. Under `SVC_SENSOR_ACQUISITION=embedded` the service polls
embedded devices itself and only registers external ones; the native Windows
Sensor Agent (`scripts/sensor_agent.py`) reads those from the same
`sensors_config.json` and posts them to `POST /sensors/ingest`. `/health`
reports an external sensor as degraded when no agent observation has arrived
or the latest is older than `stale_after_s` (default
`max(3 x interval_s, 60)` seconds). `SVC_SENSOR_ACQUISITION=external` hands
every device to the agent.

`SVC_SENSOR_INGEST_TOKEN` is required at startup under
`SVC_SENSOR_ACQUISITION=external`, and under `embedded` whenever an enabled
device is marked external. Otherwise it can stay empty, and
`POST /sensors/ingest` answers 404. The agent sends it in the
`X-Sensor-Ingest-Token` header.

Each family list (`t10a`, `jeti_spectraval`, `eko_ms90_plus`) is capped at
four entries. The service starts clients only for the first four entries of
each list, disabled entries included, and ignores the rest without a warning.
Startup validation still checks every entry, and the Windows Sensor Agent does
not apply the cap.

Use `config/production.example/sensors_config.json` as the production template.
See [production_sensor_setup.md](../docs/production_sensor_setup.md) for site
setup.

## API

The full, current endpoint reference is generated by FastAPI:

- `/api/docs`: Swagger UI for people.
- `/api/redoc`: ReDoc.
- `/api/openapi.json`: OpenAPI schema for tools.

`/docs`, `/docs/routines`, and `/docs/sensors` are the HMI's in-app docs when
the backend serves the built frontend.

Endpoints an operator checks by hand:

- `GET /health`
- `GET /sensors`
- `GET /metrics/latest`

`GET /health` returns:

```json
{
  "status": "ok",
  "environment": "development",
  "control_source": "simulated",
  "sensor_source": "simulated",
  "sensor_acquisition": "embedded",
  "sensor_status": "healthy",
  "sensor_errors": []
}
```

When any sensor client has an error, or an external sensor has no fresh agent
observation, `sensor_status` and `status` both become `degraded` and each
problem is listed in `sensor_errors` as `"<sensor_id>: <message>"`. `/health`
does not probe Halio.

Group creation, editing, and deletion are available only in development.

## Operator notes

### Halio groups created by the service

In production, the first panel listing after each service start creates a
single-window group on the Halio controller for every window that lacks one,
named after the window. Panel commands use these groups, and a panel command
also creates the group on demand if it is still missing. Existing
single-window groups are reused, so restarts do not create duplicates. The
groups persist on the controller: this is a vendor-side change that remains
after the app is removed.

### Database backups

When `SVC_DB_BACKUP_INTERVAL_HOURS` is greater than 0 and `SVC_DB_BACKUP_DIR`
is set, the service writes one backup at startup and then one every interval.
Each file is a complete SQLite copy made with the SQLite backup API and named
`<environment>-audit-YYYYMMDD-HHMMSS.db`, for example
`production-audit-20260801-020000.db`. Nothing prunes old backups. At the
Compose default of 24 hours this is one full copy of `audit.db` per day plus
one per restart, so delete old files from the host `SVC_DB_BACKUP_DIR` by hand
or with a scheduled task.

To restore:

1. Stop the container: `podman compose --env-file svc/.env.production down`.
2. Copy the current `audit.db` in `SVC_PRODUCTION_DATA_DIR` aside. If an
   `audit.db-journal` file sits next to it (left by a crash), move it aside too
   so SQLite does not replay it onto the restored database.
3. Copy the chosen backup over `SVC_PRODUCTION_DATA_DIR\audit.db`. Overwrite
   it; do not delete it first and leave the directory empty, because production
   refuses to start without an existing `audit.db`.
4. Optionally verify the restored file with `scripts/production_preflight.py`
   (see `DEV-SETUP.md`).
5. Start the container: `podman compose --env-file svc/.env.production up -d`.

### HMI mock fallback

If any of the HMI's periodic API requests fails, the HMI switches to
in-browser mock data and shows a `MOCK MODE` badge in the header. Commands made
in that state do not reach the service or Halio. See `web/README.md`.

### Routine runtime

Each routine runs as a separate `python3` subprocess started by the service. The
`python3` on the service's `PATH` must be able to import `requests`, which the
container image installs from `requirements.txt`. Routine scripts call the API
at the hard-coded `http://127.0.0.1:8000`, so routines stop working if the
service listens on a different port (`SVC_PORT`).

## Tests

```powershell
uv run pytest tests
```

Tests use a temporary runtime directory and cannot write to the production
database.
