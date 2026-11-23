# RFC: A Uniform, Modular Sensor Data Model

| Field | Value |
| :--- | :--- |
| Author | Calvin Grabowski |
| Date | 2026-11-21 (first draft 2026-10-22) |
| Status | Proposed |
| Decision Date | (fill when decided) |
| Deciders | (fill when decided: the team, with the researchers on metric names and units) |
| Superseded By | — |

## Problem and Context

The DIAL Control Center is the local software for Oregon State University's Daylighting Innovation and Analysis Lab (DIAL), a mobile research trailer with two test rooms. Researchers use it to study how daylight affects people. The software tints each room's electrochromic windows on a schedule while indoor and rooftop instruments measure the light. The researchers are not software engineers. They rely on the system to record every reading so that a study's results can be trusted and analysed later in their own tools (`docs/requirements.md`, Problem Statement). It runs on the trailer's Windows PC and stores everything in one SQLite file, `audit.db`.

This decision is about how that file stores sensor data. Three instrument kinds are supported today: Konica Minolta T-10A illuminance meters, a JETI Spectraval spectroradiometer, and an EKO solar station read through a C-BOX. Sensor data lives in four tables created by `_ensure_sensor_db` in `svc/app/state.py`:

- `sensors`: each sensor's id, kind, label, location, configuration, and active flag.
- `sensor_readings`: one row per sensor, timestamp, metric, and value.
- `sensor_spectra`: spectra stored as JSON arrays.
- `sensor_ingest_events`: duplicate protection for the Windows Sensor Agent.

Because `sensor_readings` holds one row per measurement, a new instrument needs no new columns. The problems are around that table:

- **Metric names follow no rules.** Each driver picks its own names. The T-10A writes `lux`. The JETI writes 21 metrics, such as `melanopic_edi_lx` (`svc/app/sensors/spectral_metrics.py` plus `sample_interval_s` in `jeti_spectraval_watcher.py`). The EKO writes 11, such as `ghi_w_m2` (`eko_cbox_modbus_tcp_client.py`). Units exist only as a naming habit; the database stores neither unit nor quantity. The only check on arrival is a name pattern (`MetricName` in `svc/app/models.py`).
- **Adding an instrument kind means editing shared core code.** `validate_sensor_configuration` and `_make_clients_from_config` in `svc/app/sensors/manager.py` (1,143 lines) name the three kinds explicitly, with a separate block for each. The four-device limit is enforced twice and inconsistently. Validation rejects a fifth device (`manager.py:166`), but client construction silently drops extras with `[:4]` slices (`manager.py:449`, `583`, `804`).
- **Schema changes are ad hoc.** The `active` column was added by reading `PRAGMA table_info` and running `ALTER TABLE` when it was missing. Nothing records which schema version a database file has.

**How this reaches the researchers.** Suppose a researcher exports the sensor log to CSV to compare indoor illuminance across instruments. The export has a metric column but no unit or quantity column (`SensorLogEntry` in `models.py`). They find three illuminance series:

- `lux` from the T-10A.
- `lux` from the JETI, which the instrument reports itself.
- `lux_calc` from the JETI, which the software computes from the spectrum (`spectral_metrics.py`).

Nothing in the data says the last two measure the same quantity by different methods, or that `cie1931_x` has no unit. The researcher must ask or guess. If a future driver writes `illuminance`, their filter for `lux` silently misses it.

**Why this is hard to reverse.** Driver registration code is easy to change later: a Type 2 decision, in the terms of Amazon's 2015 shareholder letter [6]. The stored vocabulary is Type 1. Once a study records readings under a name, renaming it means migrating historical rows and every analysis script built on them, or earlier results stop being comparable.

**Why now.** Every week the trailer runs, it records more study data under the current names, so every week makes a later rename more expensive. Deciding before more data and instruments arrive is the cheapest point. The team already tracks this as risk 5 in `docs/risks.md` and as an open question in `docs/requirements.md`.

**If the team does nothing,** each new instrument adds names by habit, units stay undocumented, and every addition edits the file all sensors depend on.

## Options

### Option A: Metric Catalog, Driver Registry, and Schema Versioning

Keep the one-row-per-measurement table and add three things:

- A `metric_definitions` table recording each metric's name, quantity, unit, description, and review status.
- A driver registry mapping each configuration key to its validator, client factories, and declared metrics, so `manager.py` loops over the registry instead of naming kinds.
- `PRAGMA user_version` [2] to record which migrations a database has received.

**Costs:**

- One migration.
- A refactor of `manager.py`.
- Seeding the catalog with the 33 metrics stored today.
- A rule that every driver change also updates the catalog.

**Right when:** the instrument set will change, and the stored vocabulary must stay comparable across studies.

### Option B: Catalog and Naming Rules Only

Add the `metric_definitions` table, a naming convention, and validation at ingest, but leave `manager.py` as it is.

**Costs:**

- One migration and the catalog seed.
- The per-kind blocks and the inconsistent device limit stay.
- Each new instrument kind still edits the core file.

**Right when:** no new instrument kind is planned soon. It fixes the hard-to-reverse part, the vocabulary, at the lowest cost.

### Option C: Do Nothing

Keep free-form names and per-kind blocks.

**Costs:**

- Nothing today.
- Each new instrument costs more and risks the existing drivers.
- The vocabulary drifts, with no record of units.

**Right when:** no instrument will ever be added, and the 33 current names are already documented where researchers look.

### Option D: One Wide Table per Instrument Kind

Store each kind in its own typed table, for example `t10a_readings(lux)`.

**Costs:**

- Every new instrument or metric becomes a schema migration.
- The queries behind the API (latest readings, the sensor log, CSV export) become `UNION`s that grow with each kind.
- SQLite cannot change a column's type in place; that and most other changes need the full table-rebuild procedure [4].

**Right when:** the instrument set is fixed for the life of the project, and typed columns are worth more than adding instruments cheaply.

### Option E: Move Readings to a Time-Series Database

Use a store such as InfluxDB or TimescaleDB for readings and keep SQLite for everything else.

**Costs:**

- A second service on the trailer PC, which is a new way for startup to fail in a system that must keep working when parts are missing.
- Migrating existing data, rebuilding the `db_backup.py` backup and restore path, and a license review.

**Right when:** data volume or query load outgrows SQLite on the trailer hardware, or the lab moves its data to a managed server.

## Analysis

**Performance, measured on this project.** This was not a month-long run, and it did not use real trailer logs. The script `svc/scripts/bench_sensor_month.py` generated one month of fake readings in about 18 seconds, then timed the real query functions from `state.py` against them. It used the sensor counts and reporting rates in `svc/config/production.example/sensors_config.json` (16 T-10A heads every 60 s, the JETI every 60 s, the EKO every 5 s), on a development laptop.

| Measure | Result |
| :--- | :--- |
| Rows in `sensor_readings` after one month | 7,300,800 (78% from the EKO) |
| Database size, spectra excluded | 687 MB |
| One-day range query for one metric (`fetch_readings`) | median 31 ms |
| 1,000-event ingest batch (`ingest_sensor_events`) | median 51 ms, p95 53 ms |
| Latest value of every metric (`fetch_latest_readings`) | median 868 ms, p95 873 ms |

Viewing a time range is fast: one day of one metric takes 31 ms, even with a month stored, because an index on `(sensor_id, metric, ts)` lets the query jump straight to that slice. Saving new readings is fast too. That fits SQLite's guidance that device-local storage with low writer concurrency is "almost always" better served by SQLite [3]. Options A and B leave this table and index untouched. Option E would solve a scale problem the trailer does not have yet.

Getting the latest value of every metric is slow: about 0.9 s. It is slow because it scans the entire history to find each metric's newest row, so it gets slower as `audit.db` grows, whatever the user is viewing. Every option has this problem, so it is a separate follow-up (a "latest value" table or a better index), not a reason to choose a different data model.

**Uncertainty.** The data used constant values and placeholder JETI names, and the trailer PC may be faster or slower than the laptop. I have not measured the cost of a catalog lookup during ingest. It should be small (tens of rows, cacheable), but the verification plan measures it. I also do not yet know which names the researchers' scripts use. That is why the recommendation starts with them.

**Complexity and maintainability.** Options A and B fix the vocabulary the same way. They differ only in the registry. The registry puts each instrument's knowledge in its own module behind the existing `SensorClient` protocol in `svc/app/sensors/interface.py`. That protocol is structural, so drivers need no shared base class [5]. After that, adding an instrument stops touching `manager.py` and the device-limit bug is fixed in one place. Option D moves the same knowledge into the schema. Option E adds a second system to run and back up.

**Uniformity, from outside the project.** IETF RFC 8428 (SenML) represents every sensor measurement as a name, a time, a unit drawn from a registry (for example `Cel`), and a value [1]. The catalog adopts that shape inside the database without changing the API.

**Security.** Only Option E adds network surface: a new service with its own credentials on the trailer LAN.

**Cost.** Option B is one migration. Option A adds one refactor. Neither adds a dependency. Option D costs a migration per future instrument. Option E costs the most, up front and in operations.

## Recommendation and Verification Plan

Adopt **Option A, delivered in two stages.** Stage 1 is Option B: the hard-to-reverse vocabulary, done first and done right. Stage 2, the registry, is reversible and lands before the next instrument kind is added. If no new kind is ever planned, stage 2 is deferred and the outcome is Option B.

- **Confirm names with researchers first.** Before the catalog is seeded, the 33 names, units, and quantities are reviewed with the researchers directly, or through the project partner if direct contact is not possible. Their sign-off is recorded in the seeding pull request. This prevents renaming later.
- **Version the schema.** Add `PRAGMA user_version` [2] and ordered migration functions in `svc/app/state.py`. Version 2 adds `metric_definitions(name PRIMARY KEY, quantity, unit, description, status)`. Each migration runs in one transaction.
- **Keep existing names.** Existing names stay exactly as they are, so history and API responses do not change. New names follow `<quantity>_<qualifier>_<unit>`.
- **Flag unknown metrics.** Unknown metrics are still accepted, but each is recorded as `status = 'unreviewed'` and logged.
- **Stage 2.** Replace the per-kind blocks in `manager.py` with the registry, and enforce the device limit in one place.

**How the team will know it worked:**

- **Migration test on simulated data:** a version-1 database built by `bench_sensor_month.py` upgrades to version 2 with identical row counts in all four sensor tables. The sensor list, latest-readings, log, and spectrum endpoints return identical JSON before and after.
- **Migration rehearsal on real data:** the same comparison runs on an isolated copy of a recent trailer backup, never on `audit.db` itself. It adds a per-metric row count and value sum, so real-data edge cases (gaps, odd timestamps, legacy names) appear before production.
- **Failed migration:** a migration forced to fail halfway leaves `user_version` at 1 and the row counts unchanged.
- **Catalog contract:** every metric any driver or simulator can emit is in the catalog with a unit, or is explicitly marked dimensionless. The test runs in CI (`.github/workflows/ci.yml`) and fails on an unregistered name.
- **Modularity, stage 2:** a test-only instrument kind is added with one module and one registry entry, with zero lines changed in `manager.py`.
- **Failure paths:** with an instrument unreachable, startup succeeds and `/health` reports the sensors as degraded. An unknown metric is stored and flagged, never a crash.
- **Performance:** `bench_sensor_month.py` is rerun after each stage. Ingest p95 and the range-query median must stay within 10% of the numbers above.
- **Signal to reconsider:** I review the next two pull requests that add an instrument. If either needs a kind-specific branch or bypasses the catalog, this RFC is reopened.

## Constraints

- **API contract (`AGENTS.md`):** routes, schemas, and status-code behaviour must not change. This rules out rejecting unknown metrics, so they are flagged instead. It also requires the migration tests to compare API output.
- **Licensing:** the repository is GPL-3.0 (`LICENSE`). Options A and B add no dependency, and SenML is a design reference, not code. This is a condition on Option E: a database edition's license would need a compatibility review first.
- **Research data use:** readings are study records. CI tests use simulator data and committed fixtures only. The real-data rehearsal runs on an isolated backup copy on the trailer PC or an offline team machine, never in CI and never in an AI tool, with `db_backup.py` as the rollback path.
- **Vendor and partner confidentiality:** vendor protocol details (Modbus register maps, Halio material) are not reproduced here. The change sits above the drivers and does not bypass vendor software, so instrument calibration is unaffected.

## Delegation and Validation

- **Handed to AI (Claude Code):** reading `state.py`, `models.py`, `manager.py`, and the drivers to summarize the schema; drafting option descriptions and prose; proposing tests; writing and running `bench_sensor_month.py`; and applying the revisions I chose from reviewer feedback.
- **Checks that made that reasonable:** every code claim names a file or line a reviewer can open. Each reference was opened, and its claim checked against the page on the access date listed. The benchmark is a committed script anyone can rerun. Implementation goes through CI, pull-request review, and a restorable backup.
- **Kept for myself:** choosing this decision, deciding which reviewer points to take, and making the recommendation. Researcher sign-off and the real-data rehearsal also stay with me, because they involve research data and people that no tool should handle for me.
- **Where I validated myself, and why:**
  - **Metric count.** I counted every stored metric, because the catalog seed is the new schema: a missed name becomes an unreviewed row in research data. The recount found 33, not the draft's 34, because `spectrum` goes to `sensor_spectra`.
  - **API constraint.** I checked it in `AGENTS.md`, because a status-code change would break the Windows Sensor Agent in the field.
  - **Device limit.** I read the `[:4]` slices in `manager.py`, because silently dropping a fifth instrument loses study data unnoticed.
  - **Benchmark volumes.** I compared them with the production example config, because a wrong volume would make the performance evidence meaningless.

## Decision

**Proposed.** No part of Option A is implemented on `main`. The team decides once the researchers have reviewed the metric names and units, then fills in Status, Decision Date, and Deciders and records the outcome in an ADR.

## References

1. C. Jennings, Z. Shelby, J. Arkko, A. Keranen, and C. Bormann, "Sensor Measurement Lists (SenML)," IETF RFC 8428, Aug. 2018. <https://www.rfc-editor.org/rfc/rfc8428> (accessed 2026-11-21).
2. SQLite, "PRAGMA Statements: user_version." <https://www.sqlite.org/pragma.html#pragma_user_version> (accessed 2026-11-21).
3. SQLite, "Appropriate Uses For SQLite." <https://www.sqlite.org/whentouse.html> (accessed 2026-11-21).
4. SQLite, "ALTER TABLE." <https://www.sqlite.org/lang_altertable.html> (accessed 2026-11-21).
5. I. Levkivskyi, J. Lehtosalo, and Ł. Langa, "PEP 544: Protocols: Structural subtyping (static duck typing)," 2017. <https://peps.python.org/pep-0544/> (accessed 2026-11-21).
6. J. Bezos, "2015 Letter to Shareholders," Amazon.com, Inc., Exhibit 99.1 to Form 8-K, 2016. <https://www.sec.gov/Archives/edgar/data/1018724/000119312516530910/d168744dex991.htm> (accessed 2026-11-20).
7. DIAL Control Center repository, branch `docs/rfc-0006-final-draft`: `svc/app/state.py`, `svc/app/models.py`, `svc/app/sensors/manager.py`, `svc/app/sensors/interface.py`, `svc/app/sensors/spectral_metrics.py`, `svc/scripts/bench_sensor_month.py`, `svc/config/production.example/sensors_config.json`, `docs/requirements.md`, `docs/risks.md`, `AGENTS.md`, `LICENSE`.
