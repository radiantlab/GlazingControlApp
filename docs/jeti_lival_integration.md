# JETI LiVal Production Integration

This note records the JETI Specbos/LiVal behavior observed on the production
workstation and the supported ways to bring those measurements into the
Glazing Control App.

## Observed Site State

The following was verified on July 27, 2026:

- JETI LiVal is connected to the physical Specbos 1211 through FTDI device
  `AU03CDI4A` on `COM4`.
- LiVal owns `COM4` while it is running. A second process cannot poll that port
  concurrently.
- LiVal is making one continuous measurement every minute.
- The active capture file is:
  `C:\Users\daquser\Desktop\JETI_Specbos_260722-xxx.xlsx`.
- The capture file was created shortly after the current LiVal session started
  on July 22, 2026. Its size and modification time advance immediately after
  each measurement.
- Despite the `.xlsx` suffix, the file is not an Excel workbook. It is a
  semicolon-delimited, line-oriented LiVal capture stream beginning with
  `Date and Time:;`. This is the same content shape parsed by
  `JetiSpectravalFileWatcher`.
- The file can be read concurrently when the reader permits both read and write
  sharing. Ordinary tools that request read sharing only may report that the
  file is locked.
- `lival_session.log` is also updated continuously, but it contains SDK and
  device-communication diagnostics rather than the final photometric and
  spectral measurement rows. It is not an ingestion source.
- LiVal's `LastCapturePath` setting records the most recently selected capture
  directory. It does not identify the file handle already open for the current
  capture session.

The current production Sensor Agent watches
`svc\data\jeti_capture` for `.cap` files. The active LiVal capture is on the
Desktop, so the watcher does not see it and no JETI metrics reach the API. The
HMI currently hides registered sensors that have no fresh metrics, which is why
only the live EKO sensor is visible.

JETI documents capturing as a Continuous mode feature that writes every
measurement line-by-line, including its timestamp, photometric value, and
spectral radiometric data. See the
[JETI LiVal operating instructions](https://www.jeti.com/files/content/products/spectroradiometer/Operating_Instructions_JETI_LiVal.pdf),
sections 6.1.3 and 7.3.

## Constraints

Any production solution should:

- keep one owner for `COM4`;
- avoid reading `lival_session.log` as measurement data;
- survive service and workstation restarts without duplicating rows;
- define whether existing capture history is skipped or backfilled;
- send readings through the authenticated Sensor Agent ingestion endpoint;
- keep the API container as the sole writer of `audit.db`; and
- retain a recoverable copy of LiVal's original capture data.

## Options

| Option | Live | LiVal stays open | Effort | Main trade-off |
| --- | --- | --- | --- | --- |
| 1. Capture directly into the managed data folder | Yes | Yes | Low | Requires changing LiVal's active capture target |
| 2. Add an NTFS hard-link bridge to the current file | Yes | Yes | Low/medium | Link must be refreshed if LiVal replaces the source file |
| 3. Support an explicit external host capture path | Yes | Yes | Medium | Requires acquisition/API configuration separation |
| 4. Let the Sensor Agent own `COM4` | Yes | No | Medium | LiVal cannot use the instrument concurrently |
| 5. Import closed capture files in batches | No | Yes | Low | Measurements appear only after file rotation or LiVal shutdown |

### Option 1: Managed LiVal capture

In LiVal, use `Options -> Continuous mode -> Select file for capturing` and
select:

`C:\Users\daquser\GitHub\GlazingControlApp\svc\data\jeti_capture\specbos-1211-live.cap`

This is the recommended steady-state design:

- LiVal remains the device owner and operator interface.
- The existing directory watcher and parser can ingest the rows.
- No external Desktop path or second serial connection is needed.
- Cursor files remain alongside the managed capture data.
- Production backups include the source capture and the database.

Change the target during a controlled capture transition. Preserve the current
Desktop capture as historical evidence and verify the new file advances before
retiring the old workflow.

### Option 2: NTFS hard-link bridge

Create a `.cap`-named NTFS hard link inside `svc\data\jeti_capture` that points
to the current Desktop capture file. Both paths then refer to the same bytes,
so LiVal can keep its current filename while the existing directory watcher
sees a `.cap` file.

This is the fastest no-interruption proof of value, but it needs operational
guardrails:

- Create the link before restarting the Sensor Agent. On startup, the watcher
  establishes its cursor at the current end of the file and ingests only new
  rows.
- Do not expose a five-day capture to an already-running empty directory
  watcher without first setting its cursor; otherwise it can backfill the whole
  file.
- Record the source file identity. If LiVal deletes and replaces the Desktop
  file, the hard link can remain attached to the old file and stop updating.
- Monitor capture age and alert if the linked file stops advancing.

Use this as a temporary bridge, not the preferred permanent layout.

### Option 3: Explicit external host capture path

The Sensor Agent can explicitly identify the current Desktop capture through:

`SVC_JETI_CAPTURE_PATH=C:/Users/daquser/Desktop/JETI_Specbos_260722-xxx.xlsx`

The applicable JETI configuration names that variable through:

`"capture_path_env": "SVC_JETI_CAPTURE_PATH"`

The production API container should not be given or expected to validate a
Windows Desktop path. The native Windows Sensor Agent loads the same
`.env.production` file used with Compose, reads the file, persists its cursor
under the production data directory, and sends new rows through the
authenticated ingestion endpoint.

Choose this when operators must keep LiVal captures outside the managed data
directory.

### Option 4: Direct serial acquisition

Close LiVal and configure the Sensor Agent to own the JETI connection on
`COM4`. The app then controls scheduling and obtains readings directly through
the JETI protocol.

This removes file discovery and capture-lock concerns, but LiVal cannot remain
connected at the same time. Validate the Specbos 1211 command sequence,
measurement timing, calibration mode, and recovery behavior on the physical
instrument before making it unattended production behavior.

### Option 5: Batch import

Keep the current LiVal workflow and import capture files only after LiVal closes
or rotates them. This is suitable for archival reconciliation but does not meet
the live-HMI requirement.

Volume-shadow-copy scraping of the active file is not recommended. It adds
administrator privileges, substantial I/O, and snapshot lifecycle complexity
to a file that can already be integrated more directly.

## Recommendation

1. Use Option 3 now so LiVal can keep its existing Desktop capture and filename.
2. Schedule `Get-JetiLogs.ps1` with only `-SourceFile` and `-DataDirectory` for
   an independent incremental daily backup.
3. Consider Option 1 at a future LiVal capture transition if consolidating all
   production data under `svc\data` becomes desirable.
4. Use Option 4 only if the app is intended to replace LiVal as the measurement
   owner.

## Acceptance Checks

After enabling an option:

1. Confirm the source capture size and modification time advance.
2. Confirm `agent.log` reports a successful JETI poll and ingestion delivery.
3. Confirm `GET /metrics/latest` contains fresh `SPECBOS-1` metrics.
4. Confirm the metric timestamp and lux value agree with the corresponding
   LiVal row.
5. Confirm the outbox has no growing pending backlog.
6. Restart the Sensor Agent and confirm no duplicate or missing row.
7. Confirm the Specbos card appears in the HMI and continues updating.
