# Requirements

Goals for Fall 2026, in priority order. Tick an item when it is done and
verified; link the PR or issue that closed it.

## Priorities

- **P1, protect research data.** Without reliable records, nothing else matters.
- **P2, reliable control and operation.** Glazing commands and startup must work
  for operators on the trailer.
- **P3, documentation and convenience.** Useful, but they don't put data at risk.
- **Ongoing.** Maintenance worked in alongside the rest.

## P1: Protect research data

### 1. Database backups and data ingestion

Backups are written by the DB backup worker (`svc/app/db_backup.py`) to
`SVC_DB_BACKUP_DIR` when `SVC_DB_BACKUP_INTERVAL_HOURS` is greater than 0. We
have not confirmed that they work on the trailer, or that every instrument's
readings reach `audit.db`.

- [ ] Confirm the backup worker runs in production and writes backups on
      schedule.
- [ ] Restore a backup to a scratch location and confirm it opens and holds the
      expected readings.
- [ ] Confirm that each configured instrument's readings reach `audit.db`: the
      EKO and JETI through the container, and the T-10A and serial JETI through
      the Windows Sensor Agent (`POST /sensors/ingest`).
- [ ] Record what happens when a backup or an ingest fails, and make the
      failure visible instead of silent.
- [ ] Related: #83, a deliberate bootstrap path for a new production `audit.db`.

### 2. Continuous acquisition layer

One acquisition layer records continuously whenever the software runs,
independent of studies or glazing control. Each instrument has a status
(connected, stale, failed), and dropouts are recorded as failures rather than
as gaps or valid data. Today `/health` reports staleness only for devices fed
by the Windows Sensor Agent (`svc/app/sensors/manager.py`); the EKO has no
staleness check, and there is no durable record of dropouts.

- [ ] Find where acquisition currently depends on studies or glazing control,
      and decide the design.
- [ ] Acquisition starts with the service and keeps running without a study.
- [ ] Each instrument reports connected, stale, or failed.
- [ ] Dropouts are recorded as failures with start and end times.
- [ ] Tests cover disconnected and failed instruments, and the simulator still
      works.
- [ ] Related: #43, show in the HMI why the system is degraded.

## P2: Reliable control and operation

### 3. Troubleshoot Halio

Glazing control goes through `HalioAdapter` (`svc/app/adapter.py`).

- [ ] Glazing 0-100 binary: find out why tint behaves as binary instead of
      across the 0-100 range, and whether the cause is the app, the adapter, or
      Halio.
- [ ] Requests to windows get lost: reproduce, find where requests are dropped,
      and make failures visible instead of silent.
- [ ] Tests for both fixes, including Halio being unreachable.
- [ ] Related: #82, the glazing layout in one config file, and ADR 0001, Halio
      is the source of truth for panels.

### 4. Double-click startup

Operators start the system from one icon on the trailer PC. Tracked in epic
#75.

- [ ] #68 Lifecycle script: start, stop, status, and health check. PR #97 is
      merged; the issue is still open.
- [ ] #96 Point operator docs and CI at the lifecycle script.
- [ ] #95 Fix `Start-SensorAgent.ps1` under Task Scheduler.
- [ ] Double-click wrapper and desktop shortcut.
- [ ] The Sensor Agent starts with the system when an external device is
      configured.
- [ ] One-page operator guide.
- [ ] Verified on the trailer PC.
- [ ] Optional: start the system at boot.

## P3: Documentation and convenience

### 5. Per-sensor reference (#81)

- [ ] One reference per sensor covering acquisition, storage locations, and
      data formats.

### 6. Remote access over Tailscale VPN

Open question: remote desktop to the trailer PC, or access to the HMI only?

- [ ] Decide what remote access needs to provide.
- [ ] Get approval from the project partner before installing anything on the
      trailer PC.
- [ ] Document the setup without network details or credentials, which stay
      out of the repo.

## Ongoing: Janitorial duties

Current maintenance issues:

- [ ] #86 Standardize on Docker as the single container runtime.
- [ ] #76 Clean up the Docker build.
- [ ] #59 Add ruff, Biome, and Pester checks to CI.
- [ ] #92 Fix Biome lint warnings in `web/`.
- [ ] Triage open issues still labeled `needs-triage`.
