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
| `HALIO_API_URL` | Unused | Required |
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

Relative JETI output paths resolve beneath `SVC_DATA_DIR`; paths that escape the
runtime directory are rejected. Production validates all configured physical
ports, hosts, transports, and output paths before database initialization.

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
