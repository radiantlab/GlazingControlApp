# Development and production setup

The service has two explicit environments:

- `development` uses simulated panels and sensors by default.
- `production` uses Halio and physical sensors and never falls back to simulated data.

`SVC_ENVIRONMENT` is required. The former `SVC_MODE=sim|real` contract is not
accepted.

## Prerequisites

- Python `>=3.11,<3.14`
- [uv](https://docs.astral.sh/uv/)
- Node.js 20 and npm
- Docker or Podman for container deployments

## Local development

From the repository root:

```powershell
Copy-Item svc/.env.example svc/.env
cd svc
uv sync
uv run python main.py
```

In another terminal:

```powershell
cd web
npm ci
npm run dev
```

The backend uses:

- Configuration: `svc/config/development`
- Runtime data: `svc/.runtime/development`
- Database: `svc/.runtime/development/audit.db`

These paths do not touch the production-compatible `svc/data` directory.

To test a physical device while remaining in development, set only the
required override:

```powershell
$env:SVC_DEVELOPMENT_USE_PHYSICAL_T10A = "true"
$env:SVC_DEVELOPMENT_USE_PHYSICAL_JETI = "true"
$env:SVC_DEVELOPMENT_USE_PHYSICAL_EKO = "true"
```

Normal development should leave all three values false.

## Containerized development

Use the dedicated development definition:

```powershell
podman compose -f docker-compose.development.yml up --build
```

It uses the `glazing-development-data` named volume. It does not bind
`./svc/data`.

## Production data safety

The historical Compose definition bound host `./svc/data` to container
`/app/svc/data`. Therefore the existing host `svc/data/audit.db` may contain
production history and must not be moved or deleted.

Production continues to open:

```text
/app/svc/data/audit.db
```

The upgraded deployment requires the absolute existing host directory through
`SVC_PRODUCTION_DATA_DIR`; it will not silently use a development directory.

### 1. Rotate credentials

Rotate any Halio API key stored in an older `svc/.env`. Do not reuse that file
as the new production environment file.

### 2. Create external production configuration

Copy `svc/config/production.example` to a site-owned directory outside version
control and update `sensors_config.json`.

Sensor `output_path` values are relative to the production data directory. For
example:

```json
{
  "output_path": "sensors/spectraval_1.cap"
}
```

The application validates the entire production sensor configuration before
creating or changing its database.

### 3. Create the production environment file

Copy `svc/.env.production.example` to the ignored
`svc/.env.production` and set:

- `SVC_PRODUCTION_DATA_DIR` to the absolute directory containing the existing `audit.db`.
- `SVC_PRODUCTION_CONFIG_DIR` to the external production configuration directory.
- `SVC_DB_BACKUP_DIR` to an absolute backup directory.
- The rotated Halio URL, site ID, and API key.

### 4. Verify and back up the existing database

Stop the old application, then run from the repository root:

```powershell
uv run --project svc python scripts/production_preflight.py `
  --data-dir "C:\absolute\path\to\existing\svc\data" `
  --backup-dir "C:\absolute\path\to\backups"
```

The command refuses a missing `audit.db`, runs SQLite integrity checks, prints
table counts, and creates an integrity-checked backup.

### 5. Start production

```powershell
podman compose --env-file svc/.env.production up -d --build
```

Verify:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/sensors
Invoke-RestMethod http://127.0.0.1:8000/metrics/latest
```

Health must report `environment: production`, `control_source: physical`, and
`sensor_source: physical`. Disconnected configured hardware is exposed through
`sensor_status: degraded` and `sensor_errors`; it never causes simulated
production readings.

## Tests

```powershell
cd svc
uv run pytest tests

cd ../web
npm test
npm run typecheck
npm run build
```

The backend test setup uses a temporary database and cannot write to
`svc/data/audit.db`.

## Troubleshooting

- Missing `SVC_ENVIRONMENT`: use the development example or production Compose definition.
- `SVC_MODE is no longer supported`: remove the old variable rather than mapping it silently.
- Production refuses startup: correct the reported Halio or sensor configuration error.
- Empty production database: stop immediately and verify `SVC_PRODUCTION_DATA_DIR`; do not continue with a newly created directory.
- Physical sensor unavailable after valid startup: check the cable, COM port, export path, C-BOX IP, and Modbus TCP port 502. Production does not substitute simulated readings.
