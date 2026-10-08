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

- Podman (or Docker if installed later) runs the API/UI and is the only process
  that writes `audit.db`.
- The native Windows Sensor Agent owns T-10A/JETI COM ports, watches JETI
  files, polls the EKO C-BOX, and forwards authenticated, idempotent events.

Create `svc/.env.production` from `svc/.env.production.example`. Use one long
random value for `SVC_SENSOR_INGEST_TOKEN`; the container and native agent both
load that value. Then inventory ports without opening them:

```powershell
.\scripts\sensors\Start-SensorAgent.ps1 -Command list-ports
```

After enrolling stable `port_identity` values in `sensors_config.json`, test
one bounded pass:

```powershell
.\scripts\sensors\Start-SensorAgent.ps1 -Command once
```

Run `continuous` from Task Scheduler at system startup. The task should use
`powershell.exe` with:

```text
-NoProfile -NonInteractive -ExecutionPolicy Bypass -File C:\GlazingControlApp\scripts\sensors\Start-SensorAgent.ps1 -Command continuous
```

Use **Do not start a new instance** and restart the task after a failure. The
agent retains undelivered events in its separate
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
