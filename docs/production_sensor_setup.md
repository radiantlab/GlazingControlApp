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

- the native Windows Sensor Agent owns all physical I/O
- `T10AClient` polls T-10A serial links and emits `lux`
- `JetiSpecfirmClient` polls SPECFIRM directly and parses wavelength/value ASCII pairs
- `JetiSpectravalFileWatcher` resumes file-based `.cap` ingestion from a persistent cursor
- `EkoCBoxModbusTcpClient` polls C-BOX holding registers for irradiance, sun position, GPS, and temperature
- the agent forwards authenticated, idempotent batches to the API through a
  durable outbox
- the API container is the only process that writes the production `audit.db`

## 2) Before You Go On Site

Bring or confirm access to:

- the local trailer/lab PC
- all required USB cables for each `T-10A` body and each `JETI` instrument
- `T-A20`, `T-A21`, and `AC-A412` if the T-10A heads are being used in multi-point mode
- straight CAT5 patch cables for T-10A head/adaptor runs
- Ethernet access from the local PC/network to the EKO `C-BOX`
- the C-BOX IP address, usually `192.168.2.20` on the site network
- confirmation that the C-BOX web UI is reachable from the site computer
- JETI Windows drivers and either:
  - the PC software that will write the `.cap` output path, or
  - SPECFIRM access for direct serial polling

## 3) Configure The App

Production sensor configuration is mounted read-only at:

- `/app/svc/config/sensors_config.json`

Create it from `svc/config/production.example/sensors_config.json` and store it
in the external directory selected by `SVC_PRODUCTION_CONFIG_DIR`.

### Recommended production startup

Create `svc/.env.production` from `svc/.env.production.example`. The older
`svc/.env` is a local/legacy file and is not sufficient for production compose:
production also requires the three absolute bind-mount paths and the new
`SVC_SENSOR_INGEST_TOKEN`. Generate a long random token and keep it out of
source control.

```powershell
podman compose --env-file svc/.env.production up -d
```

Docker can run the same Compose file once Docker Desktop/Engine is installed,
but it does not provide Windows COM access to the Linux container. In either
case, run physical acquisition natively:

```powershell
.\scripts\sensors\Start-SensorAgent.ps1 -Command list-ports
.\scripts\sensors\Start-SensorAgent.ps1 -Command once
.\scripts\sensors\Start-SensorAgent.ps1 -Command continuous
```

The `once` command is the enrollment smoke test. Use `continuous` as the Task
Scheduler startup action after every configured device succeeds.

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
zero or multiple ports match. If a vendor does not expose a serial number, add
`location` or retain an explicit `port` together with the available USB
identity fields.

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
   - set `heads[].head_no` to the physical head/adaptor ID
   - keep `heads[].sensor_id` and `heads[].label` aligned with the physical head location
8. Run one Sensor Agent pass and confirm the T-10A sensor reports `lux`.

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

Use this when LiVal writes its line-oriented continuous capture output to a
file the Sensor Agent can watch. Prefer a `.cap` filename in the managed data
folder. A filename suffix alone does not identify the file format.

1. Install the JETI USB driver on the local PC if it is not already installed.
2. Connect the JETI device to the PC by USB.
3. Open JETI LiVal on the PC and confirm the device is detected.
4. In LiVal, open `Options -> Continuous mode`, select `Select file for capturing`,
   and choose a new `.cap` file inside a dedicated capture folder. For example:
   `C:\path\to\svc\data\jeti_capture\specbos-1211-live.cap`.
5. Keep LiVal Continuous mode enabled. LiVal must append each measurement to the
   selected capture file; an updating LiVal session log is not measurement data
   and cannot be used by the app.
6. Record the capture folder path. Prefer watching the folder instead of one
   filename so LiVal can start a fresh capture without overwriting history.
7. Update the production `sensors_config.json`:
   - set `jeti_spectraval[].transport` to `"file"`
   - keep `jeti_spectraval[].output_path` as its managed fallback
   - set `jeti_spectraval[].capture_path_env` to
     `"SVC_JETI_CAPTURE_PATH"` for an external Windows capture file
   - set `watch_interval_s` if you want faster or slower pickup
8. Set the exact Windows path in `svc/.env.production`, for example:
   `SVC_JETI_CAPTURE_PATH=C:/Users/daquser/Desktop/JETI_Specbos_260722-xxx.xlsx`.
9. Start the API container and the native Sensor Agent.
10. Trigger or wait for a fresh JETI measurement so the capture output updates.
11. Confirm the app begins receiving JETI metrics in `GET /metrics/latest`.

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
   - set `jeti_spectraval[].port` to `"auto"`
   - add the unique `jeti_spectraval[].port_identity`
   - set `jeti_spectraval[].baudrate` to the correct device baud rate
   - set `tint_ms` and `avg_count` if the measurement timing needs adjustment
7. Start the API container, then run one Sensor Agent pass.
8. Confirm the JETI sensor appears in `GET /sensors`.
9. Confirm the JETI sensor reports `lux` and spectral/color metrics in `GET /metrics/latest`.

### JETI watch-outs

- The schematic confirms USB to the PC. The file-vs-serial choice is a software integration choice, not a different physical cable path.
- Do not run direct serial polling while LiVal is open. Windows COM ports are
  exclusive, so LiVal and the Sensor Agent cannot own the same JETI port at the
  same time. Use file transport when LiVal must remain open.
- File transport works only if the configured `output_path` exactly matches the physical file or folder on the PC.
- The backend can now recover if the watched `.cap` file or folder appears after startup, but the path still has to be correct.
- A LiVal capture may have a misleading suffix. The current site's `.xlsx` file
  is line-oriented capture text, not an Excel workbook. Directory discovery
  currently selects `.cap` files only.
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
   - default/site example: `http://192.168.2.20/`
   - use the actual C-BOX IP if it has been changed
4. Confirm the web UI shows live EKO readings under the device page.
5. Open `Modbus -> Setup` in the C-BOX web UI.
6. Confirm `Modbus TCP Access` is enabled. The site screenshots show `Allow ModbusTCP access from any IP address`.
7. Update the production `sensors_config.json`:
   - set `eko_ms90_plus[].host` to the C-BOX IP address
   - set `eko_ms90_plus[].port` to `502`
   - confirm `slave_address` is usually `1`
   - set `timeout_s` to `3.0` unless site testing needs a different value
   - leave `float_byte_order` at `ABCD` unless testing shows otherwise
8. Start the API container and run one Sensor Agent pass.
9. Confirm the EKO sensor appears in `GET /sensors`.
10. Confirm `ghi_w_m2`, `dni_w_m2`, `dhi_w_m2`, and sun-position metrics appear in `GET /metrics/latest`.

EKO config example:

```json
{
  "eko_ms90_plus": [
    {
      "sensor_id": "EKO-00",
      "device_id": "EKO-CBOX-01",
      "host": "192.168.2.20",
      "port": 502,
      "slave_address": 1,
      "float_byte_order": "ABCD",
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
- If values are present but obviously wrong, try `float_byte_order` values in this order: `ABCD`, `CDAB`, `BADC`, `DCBA`.
- `DHI` depends on the MS-90/MS-80S system being wired and operating correctly through the C-BOX.

## 7) What To Verify On The Local PC

After wiring and config:

1. Start the API container in the `production` environment.
2. Confirm the service sees all configured sensors:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/sensors
```

3. Inventory the native ports, then run a bounded acquisition pass:

```powershell
.\scripts\sensors\Start-SensorAgent.ps1 -Command list-ports
.\scripts\sensors\Start-SensorAgent.ps1 -Command once
```

4. Confirm live metrics are arriving:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/metrics/latest
```

5. Start the continuous Sensor Agent task and open the HMI to verify:
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
