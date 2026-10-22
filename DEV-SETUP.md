# Development and production setup

The service has two explicit environments:

- `development` uses simulated panels and sensors by default.
- `production` uses Halio and physical sensors and never falls back to simulated data.

`SVC_ENVIRONMENT` is required. The former `SVC_MODE=sim|real` contract is not
accepted.

## Prerequisites

- Python 3.14 (`svc/.python-version`; `uv sync` installs it if missing)
- [uv](https://docs.astral.sh/uv/)
- Node.js 24 and npm (`.nvmrc`)
- Docker or Podman for container deployments
- Production only: access to the private
  [`radiantlab/DIAL-Internal-Documentation`](https://github.com/radiantlab/DIAL-Internal-Documentation)
  repository, which you request from the project partner. It holds
  `HALIO_SITE_ID` and the project's other secrets and site-specific values.
  Development needs none of them.

## Ways to run

Each environment can run natively with uv and npm, or in a container with
Docker Compose or Podman Compose. Run commands from the repository root.

| Method | Development | Production |
|---|---|---|
| Native (uv + npm) | `svc/.env` from `svc/.env.example`. Backend `uv run python main.py` in `svc`, frontend `npm run dev` in `web`. [Steps](#native-development) | `svc/.env.production` from `svc/.env.production.example`. `npm run build` in `web`, then `uv run --env-file .env.production python main.py` in `svc`. [Steps](#native-production) |
| Docker | `docker compose -f docker-compose.development.yml up --build` [Steps](#containerized-development) | `docker compose --env-file svc/.env.production up -d --build` [Steps](#production-with-compose) |
| Podman | `podman compose -f docker-compose.development.yml up --build` [Steps](#containerized-development) | `podman compose --env-file svc/.env.production up -d --build` [Steps](#production-with-compose) |

| Method | Development | Production |
|---|---|---|
| Environment file | `svc/.env` (native) or none (Compose sets everything) | `svc/.env.production` (native and Compose) |
| HMI | `http://localhost:5173` (native), `http://localhost:8000` (Compose) | `http://localhost:8000` |
| API | `http://127.0.0.1:8000` | `http://127.0.0.1:8000` |
| Configuration | `svc/config/development` | `SVC_CONFIG_DIR` (native), `SVC_PRODUCTION_CONFIG_DIR` (Compose) |
| Database | `svc/.runtime/development/audit.db` (native), `glazing-development-data` volume (Compose) | `SVC_DATA_DIR/audit.db` (native), `SVC_PRODUCTION_DATA_DIR/audit.db` (Compose) |

Docker and Podman read the same Compose files, and `docker compose` and
`podman compose` take the same arguments. Stop a Compose deployment with the
same command and `down` in place of `up ...`, for example
`podman compose --env-file svc/.env.production down`.

Keep both files side by side: `svc/.env` for development and
`svc/.env.production` for production. Both are git-ignored. `svc/main.py`
always loads `svc/.env`, but never overrides a variable that is already set,
so `uv run --env-file .env.production` makes every production value win. A
variable missing from `svc/.env.production` falls back to its development
value, so keep every variable from the template in it. Variable defaults are
listed in [`svc/README.md`](./svc/README.md#configuration).

Production (native or Compose) works only on a machine connected to the
[Halio network](./CONTEXT.md), the trailer LAN that the Halio controller is
on. The trailer's second network, the [regular network](./CONTEXT.md), does
not reach Halio. The trailer's production machine is connected to both (a
network card on the Halio network, Ethernet to the regular network), so it
reaches Halio and the network sensors such as the EKO C-BOX. A machine
connected only to the Halio network may not reach the C-BOX. The Halio network
has no internet access, so install dependencies and build images before
connecting to it. Production controls the live Halio panels and reads physical
sensors.

## Local development

### Pre-commit setup

Install the `pre-commit` package as a standalone development tool using uv:

```powershell
uv tool install pre-commit
```

From the repository root, run the one-time setup for each new clone:

```powershell
pre-commit install
```

This installs the Git hook configured by `.pre-commit-config.yaml`. Hooks then
run automatically on staged files when committing. The first run needs internet
access to download the hook repositories and install their dependencies.

Validate the configuration and optionally check all tracked files:

```powershell
pre-commit validate-config
pre-commit run --all-files
```

The hooks check trailing whitespace, final newlines, YAML syntax, potential
secrets, and Python style with Flake8 (99-character lines, set in `.flake8`).
Whitespace hooks can modify files; review their changes and stage the intended
fixes before retrying a commit. An all-files run passes on a clean `main`, so a
failure points to your change. These hooks do not replace the backend tests or
frontend checks below.

If `pre-commit` is not found after installation, run `uv tool update-shell` and
restart the terminal.

### Native development

From the repository root, create the environment file:

```bash
cp svc/.env.example svc/.env               # Linux/macOS
```

```powershell
Copy-Item svc/.env.example svc/.env        # Windows PowerShell
```

Start the backend:

```bash
cd svc
uv sync
uv run python main.py
```

In another terminal, start the Vite dev server, which reloads the HMI on save
and calls the API at `VITE_API_BASE` (`web/.env.development`):

```bash
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
required override in `svc/.env` (or in the shell before starting):

```bash
SVC_DEVELOPMENT_USE_PHYSICAL_T10A=true
SVC_DEVELOPMENT_USE_PHYSICAL_JETI=true
SVC_DEVELOPMENT_USE_PHYSICAL_EKO=true
```

Normal development should leave all three values false.

### Containerized development

Use the dedicated development definition with either engine:

```bash
docker compose -f docker-compose.development.yml up --build
podman compose -f docker-compose.development.yml up --build
```

The image builds the HMI and serves it with the API on
`http://localhost:8000`. Compose sets every service variable, so no `.env` file
is needed; the physical-device overrides above are passed through from the
shell if set. It uses the `glazing-development-data` named volume and does not
bind `./svc/data`. Rebuild (`--build`) after code changes; there is no hot
reload in the container.

## Native production

This runs production directly on the trailer host, or on another machine
connected to the Halio network, without a container. The backend serves the
built HMI on port 8000. Run `npm ci` and `uv sync` (step 3) while you still
have internet access; after connecting to the Halio network, only the
`npm run build` and `uv run` commands are needed.

1. Create the production configuration. `svc/config/production` is git-ignored:

   ```bash
   cp -r svc/config/production.example svc/config/production
   ```

   Edit `svc/config/production/sensors_config.json` for the site hardware
   (see [docs/production_sensor_setup.md](./docs/production_sensor_setup.md)).

2. Create `svc/.env.production` from the production template. Your
   development `svc/.env` stays as it is:

   ```bash
   cp svc/.env.production.example svc/.env.production
   ```

   Set `HALIO_API_URL`, `HALIO_SITE_ID` (from
   `radiantlab/DIAL-Internal-Documentation`; see [Prerequisites](#prerequisites)),
   `SVC_DB_BACKUP_DIR` and, if any device is external,
   `SVC_SENSOR_INGEST_TOKEN`. `SVC_DATA_DIR` defaults to
   `.runtime/production`; to continue existing production history, point it at
   the directory containing that `audit.db` and run the preflight in
   [step 4](#4-verify-and-back-up-the-existing-database) first. Set
   `SVC_HOST=0.0.0.0` to reach the HMI from other machines. The "Compose bind
   mounts" variables are not used natively, so the same file also works for
   [Compose](#production-with-compose) once they are set.

3. Build the HMI, then start the backend with the production file:

   ```bash
   cd web
   npm ci
   npm run build
   cd ../svc
   uv sync
   uv run --env-file .env.production python main.py
   ```

   Without `--env-file .env.production`, `uv run python main.py` starts
   development from `svc/.env`.

4. Open `http://localhost:8000` and run the checks in
   [step 5](#5-start-production).

The JETI LiVal file input is resolved under `SVC_SENSOR_INPUT_DIR`, which
defaults to `SVC_DATA_DIR`, so a native run needs either the capture file there
or `SVC_SENSOR_INPUT_DIR` set to its directory. COM-port devices marked
external still need the Sensor Agent.

## Production with Compose

Docker and Podman follow the same steps. The data safety notes and the
preflight in step 4 also apply to a [native production](#native-production)
run that points `SVC_DATA_DIR` at existing production data.

### Production data safety

The historical Compose definition bound host `./svc/data` to container
`/app/svc/data`. Therefore the existing host `svc/data/audit.db` may contain
production history and must not be moved or deleted.

Production continues to open:

```text
/app/svc/data/audit.db
```

The upgraded deployment requires the absolute existing host directory through
`SVC_PRODUCTION_DATA_DIR`; it will not silently use a development directory.

### 1. Retire the old environment file

Production needs only two Halio values, `HALIO_API_URL` and `HALIO_SITE_ID`
(see step 3). Do not reuse an older `svc/.env` as the production environment
file; create `svc/.env.production` from the template in step 3. Compose reads
only the file passed with `--env-file`.

### 2. Create external production configuration

Copy `svc/config/production.example` to a site-owned directory outside version
control and update `sensors_config.json`.

A JETI file entry reads its capture through `input_path`. Relative values
resolve under `SVC_SENSOR_INPUT_DIR` (`/app/svc/sensor-input` in Compose), where
Compose mounts the file named by `SVC_JETI_CAPTURE_PATH`. The template already
contains:

```json
{
  "input_path": "specbos-lival.capture"
}
```

The legacy `output_path` key resolves under the production data directory and
is used only by the native Sensor Agent.

Devices the Linux container cannot open (T-10A, JETI `serial_scpi`) carry
`"acquisition": "external"` and are read by the native Windows Sensor Agent.
See [docs/production_sensor_setup.md](./docs/production_sensor_setup.md).

The application validates the entire production sensor configuration before
creating or changing its database.

### 3. Create the production environment file

Copy `svc/.env.production.example` to the ignored
`svc/.env.production` (the same file a native production run uses) and set:

- `SVC_PRODUCTION_DATA_DIR` to the absolute directory containing the existing `audit.db`.
- `SVC_PRODUCTION_CONFIG_DIR` to the external production configuration directory.
- `SVC_DB_BACKUP_DIR` to an absolute backup directory.
- `SVC_JETI_CAPTURE_PATH` to the absolute path of the active LiVal capture
  file (a file, not a directory). Compose mounts it read-only.
- `SVC_SENSOR_INGEST_TOKEN` to a long random value if any device in
  `sensors_config.json` is marked `"acquisition": "external"`. The Sensor Agent
  uses the same value. The API refuses to start without it while an enabled
  device is marked external.
- `HALIO_API_URL`: the v3 API served by the controller's admin console port,
  including the `/api/v3` prefix, for example
  `http://192.168.2.200:8083/api/v3`. It is reachable only on the Halio
  network. The old `:8084/api` endpoint no longer accepts connections.
- `HALIO_SITE_ID`: the Halio site whose windows and groups the service
  controls. Every request goes to `<HALIO_API_URL>/sites/<HALIO_SITE_ID>/...`,
  so a wrong value leaves the HMI with no panels. Copy it from the private
  [`radiantlab/DIAL-Internal-Documentation`](https://github.com/radiantlab/DIAL-Internal-Documentation)
  repository; request access from the project partner.

Every Compose bind mount uses `create_host_path: false`. The data directory,
configuration directory, and capture file must already exist. The preflight in
step 4 creates only the backup directory.

### 4. Verify and back up the existing database

Stop the old application, then run from the repository root:

```powershell
uv run --project svc python scripts/production_preflight.py `
  --data-dir "C:\absolute\path\to\existing\svc\data" `
  --backup-dir "C:\absolute\path\to\backups"
```

The command refuses a missing `audit.db`, runs SQLite integrity checks, prints
table counts, creates the backup directory if needed, and writes an
integrity-checked backup.

### 5. Start production

```bash
docker compose --env-file svc/.env.production up -d --build
podman compose --env-file svc/.env.production up -d --build
```

Follow the logs with `podman logs -f glazing-control-app` (or `docker logs`).

Verify (native runs use the same checks):

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

- Missing `SVC_ENVIRONMENT`: a native run found no environment file; create
  `svc/.env` from `svc/.env.example`, or for production pass
  `--env-file .env.production`.
- Native production reports `environment: development` or shows simulated
  panels: it was started without `--env-file .env.production`; stop it and
  use the command in [Native production](#native-production).
- Native production uses a development path or setting: that variable is
  missing from `svc/.env.production` and fell back to `svc/.env`; add it from
  `svc/.env.production.example`.
- `SVC_MODE is no longer supported`: remove the old variable rather than mapping it silently.
- Production refuses startup: correct the reported Halio or sensor configuration error.
- `/health` is `ok` but the HMI shows 0 panels and no groups: the app cannot
  reach Halio (`/health` does not probe it). Check `podman logs
  glazing-control-app` (or the native console) for `app.adapter` errors and
  confirm `HALIO_API_URL` points at `http://<controller>:8083/api/v3` and
  `HALIO_SITE_ID` is the trailer's site. A quick check from a machine on the
  Halio network:
  `curl http://<controller>:8083/api/v3/sites/<HALIO_SITE_ID>/groups` should
  return `"success":true`.
- Empty production database: stop immediately and verify `SVC_PRODUCTION_DATA_DIR`; do not continue with a newly created directory.
- Physical sensor unavailable after valid startup: check the cable, the Sensor Agent and its `port_identity` for COM devices, `SVC_JETI_CAPTURE_PATH`, the C-BOX IP, and Modbus TCP port 502. Production does not substitute simulated readings.
