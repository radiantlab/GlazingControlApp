# Requirements

What the DIAL Control Center must do, the limits it works within, and how we
will know it works. The [design](design.md) describes how the code meets these
requirements today; [risks.md](risks.md) ranks what threatens them.

## Problem Statement

Researchers in OSU's Daylighting Innovation and Analysis Lab (DIAL) study how
daylight affects people in a mobile trailer with two symmetrical test rooms.
Each room has nine electrochromic windows and one skylight driven by a Halio
controller, and indoor and rooftop instruments (EKO C-BOX, JETI
spectroradiometers, Konica Minolta T-10A illuminance meters) measure the light.
Studies need the glazing set to known tint levels on a schedule, and every
reading and command recorded so the results can be trusted afterwards. The
researchers are not software engineers.

The DIAL Control Center is the local system that controls the glazing, records
the measurements and commands, runs study routines, and reports when an
instrument or the controller is not working, so a missing reading or a failed
command is never mistaken for valid data.

## Functional Requirements

Finished requirements name the CI test that checks them (backend tests in
`svc/tests/`, frontend tests in `web/src/`). Unfinished ones have an acceptance
criterion and point at the work-plan item below that delivers them.

| ID | Requirement | Status | Acceptance |
| :--- | :--- | :--- | :--- |
| F1 | List every panel and group with its current tint. In production, panels and groups come from Halio ([ADR 0001](adr/0001-halio-is-the-source-of-truth-for-panels.md)). | Done | `test_basic.py::test_list_panels_groups`; `test_production.py::test_list_panels_from_captured_trailer_responses` |
| F2 | Set a panel or a group to a tint level from 0 to 100, refusing a second change to the same panel within the dwell time (`SVC_MIN_DWELL_SECONDS`, default 20). | Done | `test_basic.py::test_set_and_dwell`, `test_basic.py::test_group_tinting`; `api.test.ts` "sends panel commands with the expected payload" |
| F3 | Record every tint command in the audit log with time, actor, target, level, and result. | Done | `test_sqlite.py::TestAuditLogOperations` |
| F4 | Keep the last commanded tint of each panel across service restarts. | Done | `test_basic.py::test_panel_state_persistence` |
| F5 | Create, edit, and delete groups in development; production groups are managed on the Halio controller. | Done | `test_groups_api.py::test_group_crud_round_trip` |
| F6 | Read every configured instrument and store its readings in `audit.db`: the EKO C-BOX and JETI LiVal capture in the container, T-10A and serial JETI through the Windows Sensor Agent ([ADR 0002](adr/0002-the-container-owns-network-sensors-and-the-agent-owns-com-ports.md)). | Done in code; not verified on the trailer (item 1) | `test_sensor_manager.py`, `test_eko_cbox_modbus_tcp_client.py`, `test_jeti_spectraval_watcher.py`, `test_t10a_client.py` |
| F7 | Accept sensor batches from the Sensor Agent only with the ingest token, and store each observation exactly once even when a batch is retried. | Done | `test_sensor_ingest.py::test_ingestion_is_atomic_and_idempotent`, `test_endpoint_uses_constant_time_token_check`, `test_unknown_sensor_rejects_entire_batch` |
| F8 | Show live and historical readings, including spectra, in the HMI, and export audit and sensor logs as CSV. | Done | `test_sensor_spectrum.py`; `test_sqlite.py::test_fetch_sensor_log_entries_filters_and_sorts`; `api.test.ts` "builds sensor log query parameters in the request URL" |
| F9 | Run user-written study routines once or on an interval, and stop them from the HMI. | Done, untested (risk 7) | A routine started from the HMI runs, logs, and stops on request; a routine that raises is marked failed and does not stop the service. |
| F10 | Back up `audit.db` at startup and on a schedule, and restore a backup. | Backup done; restore not verified on the trailer (item 1) | `test_db_backup.py::test_backup_database_once_creates_consistent_sqlite_copy`. Restore: a trailer backup restored to a scratch location opens and holds the expected readings. |
| F11 | Report each instrument as connected, stale, or failed, and record dropouts as failures with start and end times. | Partial: errors and agent staleness only (item 2) | `test_sensor_manager.py::test_sensor_health_reports_and_clears_polling_errors`. Remaining: unplugging an instrument in the simulator shows it as failed within one polling interval, and a dropout row with start and end times is stored. |
| F12 | Apply tint across the full 0 to 100 range on the real glazing, and surface every failed Halio request in the HMI and the audit log. | Open (item 3) | On the trailer, levels 0, 25, 50, 75, and 100 each produce a distinct reported tint; a test with Halio unreachable shows the command as failed, not accepted. |
| F13 | Start and stop the whole system, including the Sensor Agent when needed, from one icon on the trailer PC. | Open (item 4) | An operator starts the system from the icon and the HMI's health check passes, with no terminal opened. |

## Non-Functional Requirements

| ID | Requirement | Acceptance |
| :--- | :--- | :--- |
| N1 | **Local-first.** Control, acquisition, and the HMI work with no internet connection. | The service, HMI, and Halio traffic stay on the trailer network; no runtime call leaves it. |
| N2 | **Degrade, don't crash.** A missing or unreachable instrument degrades `/health` instead of stopping startup or being replaced by simulated data in production. | `test_sensor_manager.py::test_production_does_not_emit_simulated_sensor_readings`, `test_sensor_health_reports_and_clears_polling_errors` |
| N3 | **Research data is never mixed or lost by configuration.** Production and development never share a data directory; production refuses to start without explicit paths ([ADR 0004](adr/0004-production-and-development-never-share-a-data-directory.md)). | `test_config.py::test_production_and_development_database_paths_are_distinct`, `test_config_and_data_directories_cannot_overlap`, `test_production_requires_explicit_paths_and_halio` |
| N4 | **Reproducible builds.** CI tests the same dependencies and runtimes the trailer runs ([ADR 0003](adr/0003-uv-lock-is-the-only-python-dependency-source.md)). | `uv sync --frozen` in `backend-tests`; `scripts/check-runtime-versions.sh` in `docker-builds` |
| N5 | **Responsiveness.** The HMI shows a new tint or reading within one polling cycle (five seconds). | Measured on the trailer during item 3. |
| N6 | **No secrets in the repository.** Site values, tokens, and network details live only in ignored local configuration. | `detect-secrets` pre-commit hook; review per `CONTRIBUTING.md` |
| N7 | **Operable by researchers.** Starting, stopping, and checking the system needs no command line. | Same as F13. |

## Constraints

Limits the project did not choose and must work within:

- **The trailer PC runs Windows**, and the service runs there in a Linux
  container, which cannot open Windows COM ports. Serial instruments (T-10A,
  serial JETI) must be read by a native Windows process ([ADR 0002](adr/0002-the-container-owns-network-sensors-and-the-agent-owns-com-ports.md)).
- **Halio v3 is unauthenticated and reachable only from the trailer's Halio
  LAN.** The service cannot reach it from elsewhere, and anything on that
  network can command the glass ([ADR 0005](adr/0005-halio-v3-is-unauthenticated-and-lan-only.md)).
- **Vendor software stays in the loop.** The team does not bypass the Halio
  controller, JETI LiVal, or instrument firmware unless the partner confirms
  calibration and accuracy are preserved.
- **Hardware access is occasional.** Work on the trailer needs an on-site visit
  with the partner; development uses the panel and sensor simulators.
- **The HTTP API is a fixed contract.** The HMI and existing study routines
  depend on it; changing routes, schemas, or status codes needs a separate,
  agreed decision ([AGENTS.md](../AGENTS.md)).
- **Data handling.** Credentials, network details, and raw sensor data stay out
  of the repository and out of unapproved AI tools ([AGENTS.md](../AGENTS.md)).
- **Team.** Four students for the 2026–27 academic year, after which the system
  passes to the next team, so setup and decisions must live in the repository.

## Success Metrics

Measured by the end of fall 2026 unless noted.

- **No lost commands:** in an on-site test of at least 50 tint commands, every
  command is either applied or shown as failed; none disappear (F12).
- **Proven recovery:** one production backup restored and checked on the
  trailer, with the procedure documented (F10).
- **Honest data:** every configured instrument reports connected, stale, or
  failed, and an unplugged instrument shows as failed rather than as a gap (F11).
- **Operator independence:** a researcher starts and stops the system from the
  icon without help (F13).
- **Safety net:** CI is green on `main`, and every merged pull request ran the
  backend, frontend, and Docker checks.

## Non-Goals

- Hosting in the cloud or depending on internet services.
- User accounts and roles; access control relies on the isolated trailer
  network until remote access is decided.
- Replacing or modifying the Halio controller, LiVal, or instrument firmware.
- Analysing study data. The system records and exports it; researchers analyse
  it in their own tools.
- Supporting more than one trailer or site.
- Changing the HTTP API.

## Open Questions

- Why does tint behave as on/off on the real glazing: the app, the adapter, or
  Halio? (item 3)
- What should remote access provide, remote desktop or the HMI only, and who
  may use it? Needs partner approval. (item 6)
- How old can a reading be before it counts as stale, and should freshness use
  the observed or the received time? (design, deferred decisions)
- How should metric names and units be standardized before more instruments
  are added? ([RFC-0006](adr/rfc-0006-uniform-modular-sensor-data-model.md))
- How long should backups be kept, and where off the trailer PC?
- When two browsers or a routine command the same panel, which one wins?

## Fall 2026 Work Plan

Goals for fall 2026, in priority order. Tick an item when it is done and
verified, and link the PR or issue that closed it. The risk register refers to
these as "requirements item N".
### Priorities

- **P1, protect research data.** Without reliable records, nothing else matters.
- **P2, reliable control and operation.** Glazing commands and startup must work
  for operators on the trailer.
- **P3, documentation and convenience.** Useful, but they don't put data at risk.
- **Ongoing.** Maintenance worked in alongside the rest.

### P1: Protect research data

#### 1. Database backups and data ingestion

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

#### 2. Continuous acquisition layer

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

### P2: Reliable control and operation

#### 3. Troubleshoot Halio

Glazing control goes through `HalioAdapter` (`svc/app/adapter.py`).

- [ ] Glazing 0-100 binary: find out why tint behaves as binary instead of
      across the 0-100 range, and whether the cause is the app, the adapter, or
      Halio.
- [ ] Requests to windows get lost: reproduce, find where requests are dropped,
      and make failures visible instead of silent.
- [ ] Tests for both fixes, including Halio being unreachable.
- [ ] Related: #82, the glazing layout in one config file, and ADR 0001, Halio
      is the source of truth for panels.

#### 4. Double-click startup

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

### P3: Documentation and convenience

#### 5. Per-sensor reference (#81)

- [ ] One reference per sensor covering acquisition, storage locations, and
      data formats.

#### 6. Remote access over Tailscale VPN

Open question: remote desktop to the trailer PC, or access to the HMI only?

- [ ] Decide what remote access needs to provide.
- [ ] Get approval from the project partner before installing anything on the
      trailer PC.
- [ ] Document the setup without network details or credentials, which stay
      out of the repo.

### Ongoing: Janitorial duties

Current maintenance issues:

- [ ] #86 Standardize on Docker as the single container runtime.
- [ ] #76 Clean up the Docker build.
- [ ] #59 Add ruff, Biome, and Pester checks to CI.
- [ ] #92 Fix Biome lint warnings in `web/`.
- [ ] Triage open issues still labeled `needs-triage`.
