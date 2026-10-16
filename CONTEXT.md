# Glossary

Terms used across the code and docs. Where a word means something different
in Halio, the hardware, or the code, the entry says which meaning applies.

## Glazing

**Panel**: One controllable electrochromic glass unit, and the app's name for it in the
API, the UI, and `audit.db`. A panel has an `id`, a `name`, and a tint `level`.
In production each panel is one Halio **window**; in development the simulator
provides panels `P01` to `P18`, plus skylights `SK1` and `SK2`.

**Window**: Halio's term for a panel. `HalioAdapter` lists the controller's v3 windows and
returns each one as a panel, using the window's UUID as the panel `id`. In the
app, prefer "panel"; use "window" only when talking about the Halio API.

**Group**: A named set of panels that are tinted together with one command. In
production, groups are Halio groups, and the app creates a single-window group
for any window that lacks one. Creating, editing, and deleting groups is
allowed only in development. See `docs/adr/0001-halio-is-the-source-of-truth-for-panels.md`.

**Room**: One of the trailer's two test rooms, `room1` and `room2`. Rooms are not stored
anywhere: `web/src/utils/panelRooms.ts` works out each panel's room from its
`id` or `name` so the UI can lay panels out by room. A panel whose room cannot
be worked out is placed in whichever room has fewer panels.

**DR/SK naming**: The panel names `panelRooms.ts` recognizes:

- `DR<room>.<n>` (also `DR-1-3` and similar) is driver window `n` in room 1 or
  2. The nine drivers of a room are shown in a 3 × 3 grid in the order
  3, 6, 9, 2, 5, 8, 1, 4, 7.
- `SK1.<room>` (also `SKYLIGHT 1.2` and similar) is the skylight in room 1 or 2.
- The simulator's `SK1` and `SK2` are the room 1 and room 2 skylights, and its
  `P01`–`P09` and `P10`–`P18` are the room 1 and room 2 windows.
- A name that only contains `ROOM 1` or `ROOM 2` is placed in that room, after
  the numbered panels.

Skylights sort before windows in each room.

## Sensors

**Head**: One light-sensing receptor of a Konica Minolta T-10A illuminance meter. Each
head reports `lux` under its own `sensor_id` (for example `T10A1-H1`) and is
addressed by its `head_no` in `sensors_config.json`.

**Body**: The T-10A meter itself, which connects to one COM port and reads one or more
heads. One body is one `T10AClient` and one `t10a` entry in
`sensors_config.json`, with its own `device_id` (for example `KM1`). The
`protocol.body_template` setting means something else: the format of the
command text sent to a head, not the meter.

**Acquisition mode**: Which process reads a sensor. With `embedded`, the API container reads the
sensor itself; with `external`, the Windows Sensor Agent reads it and posts
readings to `POST /sensors/ingest`. `SVC_SENSOR_ACQUISITION` sets the mode for
the whole service (default `embedded`), and under `embedded` a single device
can opt out with `"acquisition": "external"`. COM-port devices (the T-10A, and
JETI over `serial_scpi`) must be external in a container. See
`docs/adr/0002-the-container-owns-network-sensors-and-the-agent-owns-com-ports.md`.

**Capture**: The line-oriented, semicolon-delimited text file that JETI's LiVal software
writes while it records spectral measurements. Each row holds a date, time,
`lux`, and spectral values. `JetiSpectravalFileWatcher` reads new rows from the
active capture file, which production Compose mounts read-only from
`SVC_JETI_CAPTURE_PATH`. See `docs/jeti_lival_integration.md`.

**Cursor**: The saved read position in a capture file: a small
`<sensor_id>.glazing-cursor.json` file holding the file's path and the byte
offset of the last row ingested. On restart the watcher resumes from the cursor
if it names the same file and the offset is still within the file; otherwise
it starts from the configured initial position. The cursor is why a restart
does not ingest the same rows twice.

## Service

**Environment**: The mode the service runs in, set by the required `SVC_ENVIRONMENT`.
`development` uses the panel simulator, simulated sensors, and isolated data
and configuration directories. `production` talks to the live Halio controller
and physical sensors, requires explicit paths, and never falls back to
simulated data. See
`docs/adr/0004-production-and-development-never-share-a-data-directory.md`.

**Routine**: A user-written Python script that the service runs on a schedule to automate
tinting, for example tinting based on sensor readings. The routine manager runs
each routine as a separate `python3` subprocess that talks to the service only
over HTTP at `http://127.0.0.1:8000`. A routine runs `once`, optionally at a
set time (`run_at_ts`), or repeatedly every `interval_ms` (default 5000) in
`interval` mode. An interval routine stops after one hour unless it is
marked `indefinite`. A **saved routine** is a named script kept
for reuse.
