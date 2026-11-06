# Setup and running

This is the one place for setting up and running the app. There are two
environments, selected by the required `SVC_ENVIRONMENT`:

- `development` uses simulated panels and sensors by default.
- `production` controls the live Halio panels, reads physical sensors, and
  never falls back to simulated data.

The former `SVC_MODE=sim|real` contract is rejected. Every variable and its
default is listed in [`svc/README.md`](./svc/README.md#configuration).

## Before you start

- Python 3.14 (`svc/.python-version`; `uv sync` installs it if missing)
- [uv](https://docs.astral.sh/uv/)
- Node.js 24 and npm (`.nvmrc`)
- Docker, only for the Compose method. It is the only supported container
  runtime
  ([ADR 0007](./docs/adr/0007-docker-is-the-only-supported-container-runtime.md)).
  Podman reads the same Compose files and mirrors the commands below, but it
  is not documented or supported.

Production also needs:

- **Site values from the internal docs.** Request access to the private
  `radiantlab/DIAL-Internal-Documentation` repository from the project
  partner, then open
  [`LOCAL-DEVELOPMENT.md`](https://github.com/radiantlab/DIAL-Internal-Documentation/blob/main/LOCAL-DEVELOPMENT.md).
  Copy `HALIO_API_URL`, `HALIO_SITE_ID`, and any other site-specific values
  from there into `svc/.env.production` (step 2 below), never into this
  repository. Development needs none of them.
- **The Halio network.** Production runs only on a machine connected to the
  [Halio network](./CONTEXT.md), the trailer LAN the controller is on. The
  trailer's production machine is also on the
  [regular network](./CONTEXT.md), which reaches the EKO C-BOX. The Halio
  network has no internet, so run `npm ci`, `uv sync`, and image builds
  before connecting to it.

## Ways to run

Run commands from the repository root unless a step says otherwise.

| Method | Development | Production |
|---|---|---|
| Native (uv + npm) | [Native development](#native-development): HMI on `http://localhost:5173`, API on `http://127.0.0.1:8000` | [Start natively](#start-natively): HMI and API on `http://localhost:8000` |
| Compose | [Development with Compose](#development-with-compose): HMI and API on `http://localhost:8000` | [Start with Compose](#start-with-compose): HMI and API on `http://localhost:8000` |

Development uses `svc/.env`. Production uses `svc/.env.production`, natively
and with Compose. Keep both files side by side; both are git-ignored.

## Development

### Native development

```bash
cp svc/.env.example svc/.env               # Linux/macOS
```

```powershell
Copy-Item svc/.env.example svc/.env        # Windows PowerShell
```

Start the backend, then the Vite dev server in a second terminal. Vite
reloads the HMI on save and calls the API at `VITE_API_BASE`
(`web/.env.development`).

```bash
cd svc
uv sync
uv run python main.py
```

```bash
cd web
npm ci
npm run dev
```

The backend reads `svc/config/development` and writes only to
`svc/.runtime/development` (database `audit.db`), never to the
production-compatible `svc/data`.

To test one physical device while staying in development, set its override in
`svc/.env` or the shell. Leave all three false otherwise.

```bash
SVC_DEVELOPMENT_USE_PHYSICAL_T10A=true
SVC_DEVELOPMENT_USE_PHYSICAL_JETI=true
SVC_DEVELOPMENT_USE_PHYSICAL_EKO=true
```

### Development with Compose

```bash
docker compose -f docker-compose.development.yml up --build
```

The image builds the HMI and serves it with the API on
`http://localhost:8000`. Compose sets every service variable, so no `.env`
file is needed; the physical-device overrides above pass through from the
shell. Data lives in the `glazing-development-data` named volume, not
`./svc/data`. There is no hot reload: rerun with `--build` after code changes.
Stop with `docker compose -f docker-compose.development.yml down`.

## Production

Steps 1 to 3 are the same for both ways to start.

### 1. Create the production configuration

```bash
cp -r svc/config/production.example svc/config/production
```

`svc/config/production` is git-ignored. For Compose, you can keep it anywhere
outside version control and point `SVC_PRODUCTION_CONFIG_DIR` at it. Edit
`sensors_config.json` for the site hardware using
[`docs/production_sensor_setup.md`](./docs/production_sensor_setup.md). The
service validates the whole sensor configuration before creating or changing
its database.

- Devices the Linux container cannot open (T-10A, JETI `serial_scpi`) are
  marked `"acquisition": "external"` and need the [Sensor Agent](#5-start-the-sensor-agent).
- A JETI file entry reads `input_path` (template: `specbos-lival.capture`),
  resolved under `SVC_SENSOR_INPUT_DIR`. Compose mounts the file named by
  `SVC_JETI_CAPTURE_PATH` there; a native run defaults the directory to
  `SVC_DATA_DIR`. The legacy `output_path` key is used only by the Sensor
  Agent.

### 2. Create `svc/.env.production`

```bash
cp svc/.env.production.example svc/.env.production
```

Do not reuse an older `svc/.env` as the production file. Fill in the values
from [`LOCAL-DEVELOPMENT.md`](#before-you-start) and the template's comments:

| Variable | Native | Compose |
|---|---|---|
| `HALIO_API_URL`, `HALIO_SITE_ID` | Required | Required |
| `SVC_DB_BACKUP_DIR` | Absolute backup directory | Same; must already exist |
| `SVC_SENSOR_INGEST_TOKEN` | Long random value when any device is external | Same |
| `SVC_DATA_DIR` | Directory holding `audit.db` (default `.runtime/production`) | Not used |
| `SVC_HOST` | `0.0.0.0` to reach the HMI from other machines | Not used |
| `SVC_PRODUCTION_DATA_DIR` | Not used | Existing absolute directory holding `audit.db` |
| `SVC_PRODUCTION_CONFIG_DIR` | Not used | Absolute production config directory |
| `SVC_JETI_CAPTURE_PATH` | Not used | Absolute path of the LiVal capture file |

The API refuses to start without `SVC_SENSOR_INGEST_TOKEN` while an enabled
device is external. Compose bind mounts use `create_host_path: false`, so the
data directory, config directory, backup directory, and capture file must
already exist; the preflight in step 3 creates the backup directory.

`svc/main.py` always loads `svc/.env` but never overrides a variable that is
already set, so with `--env-file .env.production` every production value wins.
A variable missing from `svc/.env.production` falls back to its development
value, so keep every line from the template.

### 3. Back up existing production data

Skip this for a new installation. The historical Compose file bound host
`./svc/data` to `/app/svc/data`, so an existing host `svc/data/audit.db` may
hold production history: never move or delete it, and point
`SVC_PRODUCTION_DATA_DIR` (Compose) or `SVC_DATA_DIR` (native) at its
directory. Production opens `/app/svc/data/audit.db` in the container and
never falls back to a development directory.

Stop the old application, then run:

```powershell
uv run --project svc python scripts/production_preflight.py `
  --data-dir "C:\absolute\path\to\existing\svc\data" `
  --backup-dir "C:\absolute\path\to\backups"
```

It refuses a missing `audit.db`, runs SQLite integrity checks, prints table
counts, creates the backup directory if needed, and writes an
integrity-checked backup.

### 4. Start production

#### Start natively

From the repository root, build the HMI, then start the backend with the
production file. The backend serves the HMI on port 8000.

```bash
cd web
npm ci
npm run build
cd ../svc
uv sync
uv run --env-file .env.production python main.py
```

Without `--env-file .env.production`, `uv run python main.py` starts
development instead. The "Compose" rows of the table are ignored natively, so
the same file works for both methods.

#### Start with Compose

```bash
docker compose --env-file svc/.env.production up -d --build
```

Follow the logs with `docker logs -f glazing-control-app`. Stop with
`docker compose --env-file svc/.env.production down`.

### 5. Start the Sensor Agent

Only if a device is marked `"acquisition": "external"`. On the Windows host:

```powershell
.\scripts\sensors\Start-SensorAgent.ps1 -Command list-ports
.\scripts\sensors\Start-SensorAgent.ps1 -Command once
.\scripts\sensors\Start-SensorAgent.ps1 -Command continuous
```

`list-ports` lists ports without opening them, for enrolling `port_identity`.
`once` is the smoke test. Schedule `continuous` in Task Scheduler as described
in
[Continuous production acquisition](./scripts/sensors/README.md#continuous-production-acquisition),
which covers the Windows account to use and when internet is needed. The
agent loads `svc/.env.production`, so it shares the ingest token and config
directory with the service.

### 6. Verify

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/sensors
Invoke-RestMethod http://127.0.0.1:8000/metrics/latest
```

Health must report `environment: production`, `control_source: physical`, and
`sensor_source: physical`. Disconnected configured hardware shows as
`sensor_status: degraded` with `sensor_errors`; production never substitutes
simulated readings. For per-sensor acceptance checks, use
[`docs/on_site_sensor_checklist.md`](./docs/on_site_sensor_checklist.md).

## Tests and hooks

See [Exact Local Commands](./CONTRIBUTING.md#exact-local-commands). The backend
tests use a temporary database and cannot write to `svc/data/audit.db`.

## Troubleshooting

- **Missing `SVC_ENVIRONMENT`:** no environment file was found. Create
  `svc/.env` from `svc/.env.example`, or for production pass
  `--env-file .env.production`.
- **Native production shows `environment: development` or simulated panels:**
  it was started without `--env-file .env.production`.
- **Native production uses a development path or setting:** that variable is
  missing from `svc/.env.production`; add it from the template.
- **`SVC_MODE is no longer supported`:** remove the old variable.
- **Production refuses to start:** fix the reported Halio or sensor
  configuration error.
- **`/health` is `ok` but the HMI shows 0 panels and no groups:** the app
  cannot reach Halio (`/health` does not probe it). Look for `app.adapter`
  errors in the logs, and confirm `HALIO_API_URL` and `HALIO_SITE_ID` match
  `LOCAL-DEVELOPMENT.md`. From a machine on the Halio network,
  `curl <HALIO_API_URL>/sites/<HALIO_SITE_ID>/groups` should return
  `"success":true`.
- **Empty production database:** stop immediately and check
  `SVC_PRODUCTION_DATA_DIR` (or `SVC_DATA_DIR`); do not continue with a newly
  created directory.
- **A physical sensor is unavailable after startup:** check the cable, the
  Sensor Agent and its `port_identity` for COM devices,
  `SVC_JETI_CAPTURE_PATH`, the C-BOX IP, and Modbus TCP port 502. See
  [If Something Fails](./docs/on_site_sensor_checklist.md#if-something-fails).
