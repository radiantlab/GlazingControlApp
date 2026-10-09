# Scheduled sensor captures

These scripts provide host-side, append-safe captures for sensor data that does
not come from the EKO C-BOX FTP logger:

- `Start-SensorAgent.ps1` is the Task Scheduler entry point for continuous
  production acquisition and API delivery.
- `Get-T10ALogs.ps1` polls configured T-10A heads and appends daily CSV files.
- `Get-JetiLogs.ps1` incrementally backs up one active LiVal capture file.
- `Get-ModbusLogs.ps1` remains the EKO C-BOX FTP mirror.

Use the same external `sensors_config.json` mounted into the production
container. Keep the backup destination outside the repository and outside the
live `SVC_DATA_DIR`.

## Continuous production acquisition

Production uses two cooperating processes:

- Podman (or Docker if installed later) runs the API/UI with
  `SVC_SENSOR_ACQUISITION=embedded` and is the only process that writes
  `audit.db`. The container itself polls the EKO C-BOX over Modbus TCP and
  reads the LiVal capture file that Compose mounts from `SVC_JETI_CAPTURE_PATH`.
- The native Windows Sensor Agent reads the devices the container cannot reach:
  entries marked `"acquisition": "external"` in `sensors_config.json`, which
  are the T-10A bodies and any JETI using `serial_scpi`. It owns their COM
  ports and forwards authenticated, idempotent events to `POST /sensors/ingest`.

The agent reads the same `sensors_config.json` as the container (by default
`SVC_PRODUCTION_CONFIG_DIR\sensors_config.json`, or `SENSOR_AGENT_CONFIG`).
When any device is marked external it reads only those devices; when none is
marked it reads every device, which is the legacy all-external mode
(`SVC_SENSOR_ACQUISITION=external`). In the embedded setup with no device
marked external, do not run the agent: it would fall back to reading every
device, including the ones the container already polls.

Create `svc/.env.production` from `svc/.env.production.example`. When any
device is marked external, set `SVC_SENSOR_INGEST_TOKEN` to one long random
value; the container and native agent both load it, and the container refuses
to start without it while an enabled device is marked external. Then inventory
ports without opening them:

```powershell
.\scripts\sensors\Start-SensorAgent.ps1 -Command list-ports
```

The script runs the agent through [uv](https://docs.astral.sh/uv/), which
installs the Python version in `svc/.python-version` and the packages in
`svc/uv.lock` before starting. The first run on a new PC, and the first run
after pulling an update that changes either file, needs internet access; later
runs work offline. If the install fails, the script stops and says what to
check: internet access, or a running Sensor Agent task holding files in
`svc\.venv`. Without uv, the script uses an existing
`svc\.venv` only if it was built for the Python version in
`svc/.python-version`; otherwise it stops and asks you to install uv.

After enrolling stable `port_identity` values in `sensors_config.json`, test
one bounded pass:

```powershell
.\scripts\sensors\Start-SensorAgent.ps1 -Command once
```

Run `continuous` from Task Scheduler at system startup. uv installs per user,
so run the task as the Windows account that installed uv and ran the first
`list-ports` and `once` passes, with **Run whether user is logged on or not**.
A task running as `SYSTEM` or another account does not find uv. Task
Scheduler asks for that account's password once when you save the task. The
task should use `powershell.exe` with:

```text
-NoProfile -NonInteractive -ExecutionPolicy Bypass -File C:\GlazingControlApp\scripts\sensors\Start-SensorAgent.ps1 -Command continuous
```

Use **Do not start a new instance** and restart the task after a failure. To
update, end the task, pull the update, run `once` by hand, then start the task
again. The agent retains undelivered events in its separate
`svc/sensor-agent-data/outbox.db`; it never opens `audit.db`.
Operational logs rotate at 10 MiB with five retained files under
`svc/sensor-agent-data/agent.log` by default.

## Important ownership rule

A Windows COM port can have only one owner. The production service and a capture
script cannot poll the same T-10A or serial JETI at the same time.

- `Get-JetiLogs.ps1` is safe to schedule while production is running because it
  only reads newly appended complete rows from the LiVal capture file.
- Direct T-10A and JETI serial capture is intended for diagnostics or a planned
  capture window in which the Windows Sensor Agent has released those COM ports.
- The production database is the continuous, authoritative store for serial
  measurements while the agent is running. Back up `audit.db` using the
  production database backup workflow instead of scheduling a second COM owner.

All source files are read-only to these scripts. Snapshot files are written to a
temporary name, verified, and renamed atomically. Existing snapshots and CSV
rows are never overwritten.

## T-10A capture

Dry-run the exact scheduled configuration first:

```powershell
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass `
  -File C:\GlazingControlApp\scripts\sensors\Get-T10ALogs.ps1 `
  -ConfigPath C:\GlazingConfig\sensors_config.json `
  -OutputPath D:\GlazingBackups\t10a `
  -DryRun
```

Capture one reading from every configured head:

```powershell
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass `
  -File C:\GlazingControlApp\scripts\sensors\Get-T10ALogs.ps1 `
  -ConfigPath C:\GlazingConfig\sensors_config.json `
  -OutputPath D:\GlazingBackups\t10a
```

`Get-T10ALogs.ps1` writes one daily CSV per device. Each row includes the UTC
timestamp, configured IDs, configured/resolved ports, parsed lux, status, and
the lossless raw reply as Base64. `-SamplesPerHead` and
`-SampleIntervalSeconds` can create a bounded multi-sample capture.

## LiVal backup

Schedule `Get-JetiLogs.ps1` directly. It has exactly two required parameters:

- `SourceFile`: the exact active LiVal capture file.
- `DataDirectory`: the backup destination.

```powershell
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass `
  -File C:\GlazingControlApp\scripts\sensors\Get-JetiLogs.ps1 `
  -SourceFile "C:\Users\daquser\Desktop\JETI_Specbos_260722-xxx.xlsx" `
  -DataDirectory "D:\GlazingBackups\jeti"
```

The first run backs up all existing complete rows. Each later run reads only
bytes appended after the persistent cursor and writes them to a new immutable
`*.capture.txt` chunk. An incomplete row being written by LiVal is left for the
next run. Cursor state is stored under `DataDirectory\.state`, and daily
operational logs are stored directly under `DataDirectory`.

The `.xlsx` suffix is not interpreted as an Excel workbook. The script preserves
the line-oriented LiVal capture bytes exactly and can read the source while
LiVal is writing it.

The T-10A serial script accepts the application's stable selector format. An
explicit `port` opens that port. A `port` value of `"auto"` requires
`port_identity` (for example `vid`, `pid`, and preferably `serial_number`) and
must resolve to exactly one detected Windows port. The capture records both the
configured selector and resolved COM port. Dry-run validates the selector but
does not assert that the hardware is currently connected; actual capture
performs resolution before opening anything.

## EKO C-BOX log mirror

`Get-ModbusLogs.ps1` downloads the EKO C-BOX's own log files from
`/var/log/modbus` over FTP. It is independent of the service, which reads the
C-BOX live over Modbus TCP.

```powershell
.\scripts\sensors\Get-ModbusLogs.ps1 -LocalPath D:\GlazingBackups\eko
```

- Source: `ftp://192.168.40.50/var/log/modbus/` by default. Override with
  `-FtpHost` and `-RemotePath`.
- Output: `-LocalPath`, default `.\modbus_logs` relative to the current
  directory, created if missing. Subdirectories and symlinks on the C-BOX are
  skipped.
- Credentials: `-Username` and `-Password` both default to `admin`, the
  C-BOX factory default, so a plain run needs no arguments. Pass them only if
  the C-BOX login was changed.
- Skip-unchanged: a file whose local copy has the same byte count as the remote
  file is skipped. A file whose size differs is downloaded again and overwrites
  the local copy.
- Requires `curl.exe`, which ships with Windows 11.

This script has no named mutex and does not use the exit codes below; a failed
directory listing throws, and failed file downloads are reported as warnings.

## Task Scheduler

In Task Scheduler:

1. Use `powershell.exe` as the program.
2. Put `-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ...` and all
   absolute paths in **Add arguments**.
3. Run as a Windows account with read access to config/live JETI data and write
   access to the backup root.
4. Enable **Do not start a new instance**. The scripts also use a named mutex
   and return exit code `5` if an overlapping invocation gets through.
5. Run the exact command once manually and inspect the dated operational log
   before enabling the schedule.

Exit codes are:

| Code | Meaning |
| ---: | --- |
| `0` | Success, including no new complete LiVal rows |
| `2` | Configuration or invocation error |
| `5` | Another invocation owns the same output root |

## Validation

The Pester suite uses dry-run and temporary files; it never opens a COM port:

```powershell
Invoke-Pester .\scripts\sensors\tests\SensorBackupScripts.Tests.ps1
```
