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

At that time the Sensor Agent watched `svc\data\jeti_capture` for `.cap`
files. The active LiVal capture was on the Desktop, so the watcher did not see
it and no JETI metrics reached the API. The current design (see
Recommendation) mounts the active capture file into the API container instead.

The HMI keeps a registered sensor visible when it stops reporting: the card
shows its last stored readings with a "not reporting" marker.

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
- give the API container read-only access to the capture file, so it never
  modifies LiVal's data;
- keep the API container as the sole writer of `audit.db`; and
- retain a recoverable copy of LiVal's original capture data.

## Options

| Option | Live | LiVal stays open | Effort | Main trade-off |
| --- | --- | --- | --- | --- |
| 1. Capture directly into the managed data folder | Yes | Yes | Low | Requires changing LiVal's active capture target |
| 2. Add an NTFS hard-link bridge to the current file | Yes | Yes | Low/medium | Link must be refreshed if LiVal replaces the source file |
| 3. Mount the external capture file into the container | Yes | Yes | Low | Path must be updated when LiVal starts a new capture file |
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

### Option 3: Mounted external capture file

Set the exact Windows path of the active capture in `svc/.env.production`:

`SVC_JETI_CAPTURE_PATH=C:/Users/daquser/Desktop/JETI_Specbos_260722-xxx.xlsx`

`docker-compose.yml` bind-mounts that one file read-only at
`/app/svc/sensor-input/specbos-lival.capture`, with
`create_host_path: false`, so the file must exist before the container
starts. The production template's `SPECBOS-1` entry reads it through:

```json
{
  "transport": "file",
  "input_path": "specbos-lival.capture",
  "input_kind": "file"
}
```

`input_path` resolves under `SVC_SENSOR_INPUT_DIR` (`/app/svc/sensor-input` in
Compose). The container's watcher persists its cursor in the production data
directory and writes observations directly to `audit.db`. No Sensor Agent and
no ingestion token are involved.

If LiVal starts a new capture file, update `SVC_JETI_CAPTURE_PATH` and recreate
the container.

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

1. Use Option 3. LiVal keeps its existing Desktop capture and filename, and the
   API container reads the file through the read-only mount.
2. Schedule `Get-JetiLogs.ps1` with only `-SourceFile` and `-DataDirectory` for
   an independent incremental daily backup.
3. Consider Option 1 at a future LiVal capture transition if consolidating all
   production data under `svc\data` becomes desirable.
4. Use Option 4 only if the app is intended to replace LiVal as the measurement
   owner. That entry needs `"transport": "serial_scpi"` and
   `"acquisition": "external"`, because only the native Sensor Agent can open
   `COM4`.

## Acceptance Checks

After enabling an option:

1. Confirm the source capture size and modification time advance.
2. Confirm the container log (`podman logs glazing-control-app`) shows no JETI
   watcher errors.
3. Confirm `GET /health` reports no `SPECBOS-1` entry in `sensor_errors`.
4. Confirm `GET /metrics/latest` contains fresh `SPECBOS-1` metrics.
5. Confirm the metric timestamp and lux value agree with the corresponding
   LiVal row.
6. Restart the container and confirm no duplicate or missing row.
7. Confirm the Specbos card in the HMI shows current readings, not the
   "not reporting" marker, and continues updating.
