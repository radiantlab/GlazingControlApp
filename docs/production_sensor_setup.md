# Production Sensor Setup

This runbook is for the trailer/lab PC in the `production` environment.

The production implementation supports the hardware shown in the current wiring diagram and sensor manuals:

- Konica Minolta `T-10A` illuminance meters over USB/virtual COM
- JETI `spectraval 1511` and `specbos 1211-2` over either:
  - file-based `.cap` ingestion from the PC measurement workflow, or
  - direct SPECFIRM serial/virtual COM
- EKO `MS-90+` system through the `C-BOX` Ethernet Modbus TCP interface

## 1) Topology From The Site Schematic

The latest site diagram shows three distinct PC-facing paths:

- `T-10A`:
  - the diagram shows `sensor heads`, `adapter head`, and `body`
  - receptor heads connect to the body through the Konica Minolta adapter/head chain and straight CAT5 cabling
  - the body connects to the local PC by USB
- `JETI spectraval/specbos`:
  - the diagram shows `Spectravals (1511)` and `Specbos 1211`
  - each instrument connects directly to the local PC by USB
  - the schematic confirms the USB hardware path; the backend can then use either a file-based `.cap` workflow or direct SPECFIRM serial
- `EKO MS-90+`:
  - the diagram shows a solar-station assembly with `MS-80S`, `MS-90+ DNI`, `C-BOX`, `DAC`, and power supply
  - the MS-90 DNI sensor and optional MS-80S feed the `C-BOX`
  - the PC talks to the `C-BOX` over Ethernet using Modbus TCP
  - the app does not use the old USB-to-RS485 / COM-port EKO path anymore
  - the app does not configure a separate DAC interface; the backend-facing link is the `C-BOX` Ethernet interface

That matches the production acquisition architecture now:

- Compose runs the API container with `SVC_SENSOR_ACQUISITION=embedded`. The
  container reads every device it can reach from Linux:
  - `EkoCBoxModbusTcpClient` polls C-BOX holding registers over Modbus TCP for
    irradiance, sun position, GPS, and temperature
  - `JetiSpectravalFileWatcher` reads the LiVal capture file that Compose
    bind-mounts read-only from `SVC_JETI_CAPTURE_PATH` to
    `/app/svc/sensor-input/specbos-lival.capture`, resuming from a persistent
    cursor
- The Linux container cannot open Windows COM ports. A device that needs one
  (T-10A, or JETI with `transport: "serial_scpi"`) is marked
  `"acquisition": "external"` in `sensors_config.json`. The API registers its
  sensors but does not poll them.
- The native Windows Sensor Agent (`svc/scripts/sensor_agent.py`, started by
  `scripts/sensors/Start-SensorAgent.ps1`) reads the same `sensors_config.json`
  and polls only the devices marked external:
  - `T10AClient` polls T-10A serial links and emits `lux`
  - `JetiSpecfirmClient` polls SPECFIRM directly and parses wavelength/value
    ASCII pairs
- The agent forwards authenticated, idempotent batches to
  `POST /sensors/ingest` through a durable outbox.
- `/health` reports an external sensor as degraded when no agent observation
  has arrived or the latest is older than `stale_after_s` (default
  `max(3 x interval_s, 60)` seconds).
- The API container is the only process that writes the production `audit.db`.

If no device is marked external, the agent is not needed.

## 2) Before You Go On Site

Bring or confirm access to:

- the local trailer/lab PC
- all required USB cables for each `T-10A` body and each `JETI` instrument
- `T-A20`, `T-A21`, and `AC-A412` if the T-10A heads are being used in multi-point mode
- straight CAT5 patch cables for T-10A head/adaptor runs
- Ethernet access from the local PC/network to the EKO `C-BOX`
- the C-BOX IP address, `192.168.40.50` on the trailer network
- confirmation that the C-BOX web UI is reachable from the site computer
- JETI Windows drivers and either:
  - LiVal, which will write the capture file mounted through `SVC_JETI_CAPTURE_PATH`, or
  - SPECFIRM access for direct serial polling

## 3) Configure The App

Production sensor configuration is mounted read-only at:

- `/app/svc/config/sensors_config.json`

Create it from `svc/config/production.example/sensors_config.json` and store it
in the external directory selected by `SVC_PRODUCTION_CONFIG_DIR`.

### Recommended production startup

Create `svc/.env.production` from `svc/.env.production.example`. The older
`svc/.env` is a local/legacy file and is not sufficient for production compose:
production requires four absolute host paths, all mounted with
`create_host_path: false`, so each must already exist:

- `SVC_PRODUCTION_DATA_DIR`: the directory containing the existing `audit.db`
- `SVC_PRODUCTION_CONFIG_DIR`: the directory containing `sensors_config.json`
- `SVC_DB_BACKUP_DIR`: the database backup directory
- `SVC_JETI_CAPTURE_PATH`: the active LiVal capture file (a file, not a folder)

`SVC_SENSOR_INGEST_TOKEN` is required whenever an enabled device is marked
`"acquisition": "external"`, because the Sensor Agent then posts to
`POST /sensors/ingest`. The API refuses to start without it in that case.
Generate a long random token and keep it out of source control. With no
external devices it can stay empty.

```powershell
podman compose --env-file svc/.env.production up -d --build
```

`docker compose` takes the same arguments. Neither Podman nor Docker gives the
Linux container Windows COM access. If any device is marked external, run the
Sensor Agent natively on the Windows host:

```powershell
.\scripts\sensors\Start-SensorAgent.ps1 -Command list-ports
.\scripts\sensors\Start-SensorAgent.ps1 -Command once
.\scripts\sensors\Start-SensorAgent.ps1 -Command continuous
```

The agent loads `svc/.env.production`, so it gets the same
`SVC_SENSOR_INGEST_TOKEN` as the container, and it defaults its config to
`SVC_PRODUCTION_CONFIG_DIR/sensors_config.json` (override with
`SENSOR_AGENT_CONFIG`). There is no separate agent config file. When any device
is marked external, the agent reads only the marked devices.

The `once` command is the enrollment smoke test. Use `continuous` as the Task
Scheduler startup action after every external device succeeds.

### Stable COM enrollment

COM numbers alone are not device identities and can change after reconnecting a
USB cable. `list-ports` is metadata-only: it never opens a port or sends bytes.
For every T-10A or direct-serial JETI, copy the reported `vid`, `pid`, and
preferably `serial_number` into the device configuration:

```json
{
  "port": "auto",
  "port_identity": {
    "vid": "0x0403",
    "pid": "0x6001",
    "serial_number": "AU03CDI4A"
  }
}
```

Use the actual identity printed for that instrument. Resolution fails closed if
zero or multiple ports match. Allowed `port_identity` fields are `vid`, `pid`,
`serial_number`, `manufacturer`, `product`, `location`, and `hwid`. If a vendor
does not expose a serial number, add `location` or retain an explicit `port`
together with the available USB identity fields.

### Enabling the template's T-10A entries

The production template already contains two T-10A bodies, `KM1` (sensors
`T10A1-H1` to `T10A1-H8`) and `KM2` (`T10A2-H1` to `T10A2-H8`). Both are
`"enabled": false`, `"acquisition": "external"`, and `"port": "auto"` with a
placeholder `port_identity`. To use them:

1. Set `"enabled": true` on each connected body.
2. Replace `"serial_number": "replace-with-usb-serial"` with the identity that
   `list-ports` reports for that body.
3. Set `SVC_SENSOR_INGEST_TOKEN` in `svc/.env.production` and recreate the
   container so it picks up the token.
4. Start the Sensor Agent on the Windows host (`once`, then `continuous`).

Keep `"acquisition": "external"` on these entries. Without it the container
tries to resolve the COM port itself, finds none, skips the device, and
`/health` reports the error.

## 4) T-10A Setup

The app supports one practical connection path for `T-10A`: head chain to T-10A body, then body to PC by USB.

### Method A: Single-head T-10A to PC

1. Place the `T-10A` body near the local PC.
2. Connect the receptor head to the T-10A body using the correct Konica Minolta head/adaptor hardware.
3. If any CAT5 segment is used in the chain, use straight CAT5/10Base-T patch cable only.
4. Connect the T-10A body to the PC by USB.
5. Power on the T-10A body and confirm it is detected by Windows.
6. Run `Start-SensorAgent.ps1 -Command list-ports` and record the body's
   stable USB identity.
7. Update the production `sensors_config.json`:
   - set `t10a[].port` to `"auto"` and add the unique `port_identity`
   - keep `t10a[].acquisition` at `"external"`
   - set `heads[].head_no` to the physical head/adaptor ID
   - keep `heads[].sensor_id` and `heads[].label` aligned with the physical head location
8. Confirm `SVC_SENSOR_INGEST_TOKEN` is set, run one Sensor Agent pass, and
   confirm the T-10A sensor reports `lux`.

### Method B: Multi-head T-10A to PC

1. Place the `T-10A` body near the local PC.
2. Connect each receptor head through the required `T-A20` / `T-A21` adapter chain.
3. Use straight CAT5/10Base-T patch cable between the multi-point components.
4. Connect the `AC-A412` external power supply for the multi-head setup.
5. Assign a unique physical ID to each head/adaptor. The supported range is `00` through `29`.
6. Connect the T-10A body to the PC by USB.
7. Run `Start-SensorAgent.ps1 -Command list-ports` and record its stable USB
   identity for that T-10A body.
8. Update the production `sensors_config.json`:
   - set `port` to `"auto"` and add the unique `port_identity`
   - keep `acquisition` at `"external"`
   - set each `heads[].head_no` to the actual physical ID
   - keep each `sensor_id` and `label` tied to the installed head location
9. Run one Sensor Agent pass and verify every configured T-10A head appears in
   `GET /sensors`.
10. Confirm each head produces `lux` in `GET /metrics/latest`, then start the
    continuous task.

### T-10A watch-outs

- Do not use crossover Ethernet cables.
- Multi-head mode needs external power.
- If `head_no` does not match the physical head/adaptor ID, the service will poll the wrong head or no head.
- USB COM assignments can change. Stable identity enrollment lets the agent
  follow the same instrument to its new COM number.

## 5) JETI Setup

The app supports both `spectraval 1511` and `specbos 1211-2`.

There are two supported connection methods in the app: file-based ingestion and direct serial polling. The physical cable to the PC is USB in both cases.

The production workstation's observed LiVal behavior, active capture file, and
integration alternatives are documented in
[`jeti_lival_integration.md`](./jeti_lival_integration.md).

### Method A: JETI over USB with file-based capture ingestion

Production reads one LiVal capture, from the Specbos (`SPECBOS-1`). The two
Spectravals from the old site config (`SPECTRAVAL-1`, `SPECTRAVAL-2`, kept in
`docs/reference/sensors_config.legacy-site.json`) are left out on purpose:
each file source needs its own read-only capture mount in
`docker-compose.yml`, and Compose cannot start with a missing file mount. To
bring one back, add its entry with its own `input_path` and a matching mount,
or read it over SPECFIRM as an external device (Method B).

Use this when LiVal writes its line-oriented continuous capture output to a
file. LiVal stays open and owns the USB port. The API container reads the
capture file through a read-only bind mount; the Sensor Agent is not involved.
A filename suffix alone does not identify the file format.

1. Install the JETI USB driver on the local PC if it is not already installed.
2. Connect the JETI device to the PC by USB.
3. Open JETI LiVal on the PC and confirm the device is detected.
4. In LiVal, open `Options -> Continuous mode`, select `Select file for capturing`,
   and choose the capture file.
5. Keep LiVal Continuous mode enabled. LiVal must append each measurement to the
   selected capture file; an updating LiVal session log is not measurement data
   and cannot be used by the app.
6. Set the exact Windows path of that file in `svc/.env.production`, for example:
   `SVC_JETI_CAPTURE_PATH=C:/Users/daquser/Desktop/JETI_Specbos_260722-xxx.xlsx`.
   Compose mounts it read-only at
   `/app/svc/sensor-input/specbos-lival.capture`. The file must exist before
   the container starts (`create_host_path: false`).
7. Keep the template's `SPECBOS-1` entry in the production `sensors_config.json`:
   - `jeti_spectraval[].transport` is `"file"`
   - `jeti_spectraval[].input_path` is `"specbos-lival.capture"`, which
     resolves under `SVC_SENSOR_INPUT_DIR` (`/app/svc/sensor-input` in Compose)
   - `jeti_spectraval[].input_kind` is `"file"`
   - set `watch_interval_s` if you want faster or slower pickup
8. Start or recreate the API container.
9. Trigger or wait for a fresh JETI measurement so the capture output updates.
10. Confirm the app begins receiving JETI metrics in `GET /metrics/latest`.

`input_path` is the container key. The legacy `output_path` key (resolved
under the data directory) and `capture_path_env` (names an environment
variable holding the path) are read only by the Sensor Agent's file transport,
which applies only to a JETI file entry marked `"acquisition": "external"`.

### Method B: JETI over USB virtual COM with direct SPECFIRM polling

Use this when you want the backend to talk to the JETI device directly instead of reading exported files.

1. Install the JETI USB driver on the local PC if needed.
2. Connect the JETI device to the PC by USB.
3. Run `Start-SensorAgent.ps1 -Command list-ports`.
4. Record the JETI virtual port's stable USB identity.
5. Decide which device model is connected:
   - `spectraval 1511` typically uses `921600`
   - `specbos 1211-2` typically uses `115200`
6. Update the production `sensors_config.json`:
   - set `jeti_spectraval[].transport` to `"serial_scpi"`
   - set `jeti_spectraval[].acquisition` to `"external"`
   - set `jeti_spectraval[].port` to `"auto"`
   - add the unique `jeti_spectraval[].port_identity`
   - set `jeti_spectraval[].baudrate` to the correct device baud rate
   - set `tint_ms` and `avg_count` if the measurement timing needs adjustment
7. Set `SVC_SENSOR_INGEST_TOKEN`, start the API container, then run one Sensor
   Agent pass.
8. Confirm the JETI sensor appears in `GET /sensors`.
9. Confirm the JETI sensor reports `lux` and spectral/color metrics in `GET /metrics/latest`.

### JETI watch-outs

- The schematic confirms USB to the PC. The file-vs-serial choice is a software integration choice, not a different physical cable path.
- Do not run direct serial polling while LiVal is open. Windows COM ports are
  exclusive, so LiVal and the Sensor Agent cannot own the same JETI port at the
  same time. Use file transport when LiVal must remain open.
- File transport works only if `SVC_JETI_CAPTURE_PATH` exactly matches the
  file LiVal is currently appending to. If LiVal starts a new capture file,
  update the path and recreate the container.
- A LiVal capture may have a misleading suffix. The current site's `.xlsx` file
  is line-oriented capture text, not an Excel workbook. The mounted entry uses
  `input_kind: "file"`, so the suffix does not matter. Directory discovery
  (an `input_path` folder) selects `.cap` files only.
- `lival_session.log` contains diagnostic calls, not the final measurement
  records, and must not be used as the measurement source.
- Direct serial mode requires the correct COM port and baudrate before anything else will work.
- The backend now parses SPECFIRM format `2` correctly as `wavelength<TAB>value` pairs.

## 6) EKO MS-90+ / C-BOX Setup

The app supports one physical connection path for EKO: the sensors wire into the `C-BOX`, and the PC talks to the `C-BOX` over Ethernet using Modbus TCP. The old USB-to-RS485 / COM-port method is not used by the app.

### Method A: MS-90 plus optional MS-80S into C-BOX, then C-BOX Ethernet to PC/network

1. Confirm the EKO sensors are wired into the `C-BOX` and powered according to the EKO site wiring.
2. Connect the `C-BOX` Ethernet port to the same local network as the site computer.
3. On the site computer, open the C-BOX web UI in a browser:
   - trailer C-BOX: `http://192.168.40.50/`
   - use the actual C-BOX IP if it has been changed
4. Confirm the web UI shows live EKO readings under the device page.
5. Open `Modbus -> Setup` in the C-BOX web UI.
6. Confirm `Modbus TCP Access` is enabled. The site screenshots show `Allow ModbusTCP access from any IP address`.
7. Update the production `sensors_config.json`:
   - set `eko_ms90_plus[].host` to the C-BOX IP address (`192.168.40.50` in
     the trailer; the template has a `192.0.2.10` placeholder)
   - set `eko_ms90_plus[].port` to `502`
   - confirm `slave_address` is usually `1`
   - set `timeout_s` to `3.0` unless site testing needs a different value
   - keep `float_byte_order` at `CDAB` from the template; the trailer C-BOX
     needs it, and the code default (`ABCD`) produces wrong values on it
   - leave `acquisition` unset; the container polls the C-BOX itself
8. Start or recreate the API container.
9. Confirm the EKO sensor appears in `GET /sensors`.
10. Confirm `ghi_w_m2`, `dni_w_m2`, `dhi_w_m2`, and sun-position metrics appear in `GET /metrics/latest`.

EKO config example:

```json
{
  "eko_ms90_plus": [
    {
      "sensor_id": "EKO-00",
      "device_id": "EKO-CBOX-01",
      "host": "192.168.40.50",
      "port": 502,
      "slave_address": 1,
      "float_byte_order": "CDAB",
      "interval_s": 5,
      "timeout_s": 3.0,
      "label": "EKO MS-90+",
      "location": "Roof"
    }
  ]
}
```

### EKO watch-outs

- The PC does not connect directly to `MS-90` or `MS-80S`.
- Do not configure a COM port for EKO. `eko_ms90_plus[].port` is the TCP port, usually `502`.
- If the C-BOX web UI is unreachable, fix local network/IP access before starting the backend.
- If the web UI works but the backend logs Modbus read failures, confirm Modbus TCP access is enabled in the C-BOX UI and that firewalls allow TCP `502`.
- If values are present but obviously wrong, confirm `float_byte_order` is `CDAB`. On a different C-BOX, try `CDAB`, `ABCD`, `BADC`, `DCBA` in that order.
- `DHI` depends on the MS-90/MS-80S system being wired and operating correctly through the C-BOX.

## 7) What To Verify On The Local PC

After wiring and config:

1. Start the API container in the `production` environment:

```powershell
podman compose --env-file svc/.env.production up -d --build
```

2. Confirm the service sees all configured sensors and reports their health:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/sensors
```

3. If any device is marked `"acquisition": "external"`, inventory the native
   ports, then run a bounded acquisition pass:

```powershell
.\scripts\sensors\Start-SensorAgent.ps1 -Command list-ports
.\scripts\sensors\Start-SensorAgent.ps1 -Command once
```

4. Confirm live metrics are arriving:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/metrics/latest
```

5. If the agent is in use, start its continuous Task Scheduler task. Then open
   the HMI to verify:
   - every sensor card shows current values
   - every sensor graph updates
   - `Logs -> Sensor log` fills with new rows
6. Export a CSV from the sensor log tab and confirm it contains:
   - timestamp
   - sensor ID
   - sensor kind
   - sensor label
   - metric
   - value

## 8) Expected Production Metrics

### T-10A

- `lux`

### JETI

- `lux`
- `lux_calc`
- `cie1931_x`
- `cie1931_y`
- `cct_ohno_k`
- `cct_robertson_k`
- `duv_ohno`
- `duv_robertson`
- `cri_ra`
- `cfi_rf`
- alpha-opic irradiance and EDI metrics
- `sample_interval_s` in file-watcher mode when consecutive timestamps are available

### EKO C-BOX

- `ghi_w_m2`
- `dni_w_m2`
- `dhi_w_m2`
- `board_temp_c`
- `sensor_temp_c`
- `gps_timestamp_s`
- `gps_satellites`
- `latitude_deg`
- `longitude_deg`
- `sun_elevation_deg`
- `sun_azimuth_deg`

## 9) Data Storage

Sensor metadata and time-series readings are stored in the production host
directory selected by `SVC_PRODUCTION_DATA_DIR`; inside the container this is:

- `/app/svc/data/audit.db`

The native agent's retry queue is separate:

- `svc/sensor-agent-data/outbox.db` by default

The agent never writes `audit.db`, and the API never writes the outbox.

Relevant tables:

- `sensors`
- `sensor_readings`

Host-side scheduled capture scripts are documented in
[`scripts/sensors/README.md`](../scripts/sensors/README.md). Use JETI file
snapshots while production is running. Do not schedule direct T-10A or JETI
serial capture concurrently with the Sensor Agent because Windows COM ports are
exclusive; the database backup is the continuous backup path for those live
readings.

The UI reads that data through:

- `GET /sensors`
- `GET /metrics/latest`
- `GET /metrics/history`
- `GET /logs/sensors`
- `GET /logs/sensors/export`
