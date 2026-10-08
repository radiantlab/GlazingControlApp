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

| Variable | Development default | Production |
|---|---|---|
| `SVC_ENVIRONMENT` | Required | Required |
| `SVC_DATA_DIR` | `.runtime/development` | Required mounted data directory |
| `SVC_CONFIG_DIR` | `config/development` | Required read-only config directory |
| `SVC_MIN_DWELL_SECONDS` | `20` | `20` unless overridden |
| `SVC_DB_BACKUP_INTERVAL_HOURS` | `0` | Compose default `24` |
| `SVC_DB_BACKUP_DIR` | Disabled | Required by production Compose |
| `SVC_SENSOR_INPUT_DIR` | `SVC_DATA_DIR` | Compose sets `/app/svc/sensor-input` |
| `SVC_SENSOR_ACQUISITION` | `embedded` | Compose sets `embedded` |
| `SVC_SENSOR_INGEST_TOKEN` | Empty (ingestion disabled) | Required when any device is `"acquisition": "external"` |
| `HALIO_API_URL` | Unused | Required, Halio v3 base URL (`http://<controller>:8083/api/v3`) |
| `HALIO_SITE_ID` | Unused | Required |
| `HALIO_API_KEY` | Unused | Required |

Physical-device testing in development is opt-in:

- `SVC_DEVELOPMENT_USE_PHYSICAL_T10A=true`
- `SVC_DEVELOPMENT_USE_PHYSICAL_JETI=true`
- `SVC_DEVELOPMENT_USE_PHYSICAL_EKO=true`

Health reports `sensor_source: mixed` when any override is enabled.

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

Use `config/production.example/sensors_config.json` as the production template.
See [production_sensor_setup.md](../docs/production_sensor_setup.md) for site
setup.

## API

`GET /health` returns:

```json
{
  "status": "ok",
  "environment": "development",
  "control_source": "simulated",
  "sensor_source": "simulated",
  "sensor_status": "healthy",
  "sensor_errors": []
}
```

Other primary endpoints:

- `GET /panels`, `GET /groups`
- `POST /commands/set-level`
- `GET /sensors`
- `GET /metrics/latest`, `GET /metrics/history`
- `GET /logs/audit`, `GET /logs/sensors`

Group creation, editing, and deletion are available only in development.

## Tests

```powershell
uv run pytest tests
```

Tests use a temporary runtime directory and cannot write to the production
database.
