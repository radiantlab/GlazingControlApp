# Real Sensor Setup (On Site)

This runbook assumes you are on the trailer/lab PC and want real-time data in `SVC_MODE=real`.

## 0) Sim Preview (No Hardware)

If you want to preview the exact HMI behavior before going on site, run:

```powershell
$env:SVC_MODE = "sim"
uv run python main.py
```

In sim mode the service now produces live sample data for:

- T-10A
- JETI
- EKO MS-90+

The HMI will show:

- live numeric metrics for every registered sensor
- one live graph per sensor with a metric dropdown
- live sensor logs in `Logs -> Sensor log` with CSV export

## 1) Start in Real Mode

From `svc/`:

```bash
set SVC_MODE=real
set SENSORS_CONFIG_FILE=svc/data/sensors_config.json
uv run python main.py
```

If you are using PowerShell:

```powershell
$env:SVC_MODE = "real"
$env:SENSORS_CONFIG_FILE = "svc/data/sensors_config.json"
uv run python main.py
```

## 2) T-10A (Konica Minolta)

### Physical connection

1. Connect each T-10A body to the PC (USB cable T-A15 from manual).
2. Daisy-chain receptor heads to each body using straight CAT5/10Base-T patch cables.
3. In Windows Device Manager, note each COM port (`COMx`) for each body.

### App config (`svc/data/sensors_config.json`)

Set one `t10a` entry per body:

- `port`: the COM port for that body (`COM3`, `COM4`, etc.)
- `heads`: one entry per head (`head_no`, `sensor_id`, `label`)
- optional protocol tuning is under `protocol`

### Verify

- `GET /sensors` should show `kind: "t10a"` with each head sensor ID.
- `GET /metrics/latest` should show `metric: "lux"` for each head.

## 3) JETI spectraval

Two supported real transports:

## A) File transport (recommended if LiVal is already used)

### Physical/software path

1. Connect spectraval to PC by USB (or Bluetooth/LAN per JETI docs).
2. In JETI software workflow, ensure measurements are continuously saved to a `.cap` output file/folder.

### App config

In `jeti_spectraval` entry:

- `transport: "file"`
- `output_path`: file or directory watched by backend
- `watch_interval_s`: watcher polling interval

### Verify

- `GET /metrics/latest` should show `JETI-xx` metrics (`lux`, CCT, CRI, melanopic EDI, etc.).

## B) Direct serial SCPI transport (SPECFIRM)

### Physical connection

1. Connect spectraval by USB.
2. Find COM port in Device Manager.

### App config

Set `transport: "serial_scpi"` and fill:

- `port`
- `baudrate` (default `921600` for spectraval 1511)
- optional: `tint_ms`, `avg_count`, `wavelength_start_nm`, `wavelength_end_nm`, `wavelength_step_nm`

### Verify

- `GET /metrics/latest` returns `JETI-xx` metrics.

## 4) EKO MS-90+ (via C-BOX Modbus RTU)

Backend reads the C-BOX directly over RS-485 Modbus RTU.

### Physical wiring (C-BOX output cable)

Use a USB-to-RS485 interface and 12V supply:

1. `Brown` -> +12V supply
2. `White` -> supply ground (0V)
3. `Blue` -> Modbus `A` / `+` (to RS485 adapter A/+)
4. `Black` -> Modbus `B` / `-` (to RS485 adapter B/-)
5. `Grey` -> NC

At network end, keep a 120 ohm termination resistor across A/B if needed by your RS-485 topology.

### C-BOX sensor-side wiring

MS-90 and MS-80S wiring to C-BOX should follow EKO terminal table in `docs/SensorDocs/c-box-manual.pdf`.

### App config

In `eko_ms90_plus` entry:

- `port`: COM port of USB-RS485 adapter
- `baudrate`: default `9600`
- `slave_address`: default `1`
- `float_byte_order`: default `ABCD` (change if values look byte-swapped)

### Verify

- `GET /metrics/latest` for `EKO-xx` should include:
  - `dni_w_m2`
  - `ghi_w_m2`
  - `dhi_w_m2`
  - `sun_elevation_deg`, `sun_azimuth_deg`
  - `latitude_deg`, `longitude_deg`
  - `board_temp_c`

## 5) Quick Acceptance Check

After all wiring/config:

1. Start backend in real mode.
2. `GET /sensors` returns all configured sensor IDs.
3. `GET /metrics/latest` updates for:
   - T-10A head lux
   - JETI metrics
   - EKO irradiance metrics
4. Open HMI and confirm each sensor card shows live numbers and one live graph.
5. In HMI `Logs -> Sensor log`, verify new rows appear every polling cycle.
6. Export CSV from sensor log tab and confirm file includes timestamp, sensor ID, kind, metric, and value.
7. Run 5-10 minutes and confirm timestamps continue advancing.

## 6) How The System Works Per Sensor

### T-10A

- Real mode: `T10AClient` opens COM port (`7E1`), sends command frames, parses lux per head.
- Sim mode: `T10ASimClient` generates realistic lux per configured head.
- Metric source: `lux` is directly measured (real) or generated (sim), and is not computed from other sensors.

### JETI

- Real mode:
  - `transport=file`: watcher reads `.cap` output.
  - `transport=serial_scpi`: direct SCPI serial polling.
- Sim mode:
  - sim writer creates CAP rows; watcher reads them.
- Metric source:
  - direct: `lux` (plus raw spectrum coming from the JETI path).
  - computed from spectrum: CIE xy, alpha-opic irradiances, alpha-opic EDI, CCT, Duv, CRI, CFI, `lux_calc`, `sample_interval_s`.

### EKO MS-90+ / C-BOX

- Real mode: `EkoCBoxModbusClient` polls Modbus holding registers.
- Sim mode: `EkoMs90PlusSimClient` generates the equivalent metric set.
- Metric source: values are direct register telemetry in real mode (`GHI`/`DNI`/`DHI`/temperature/GPS/sun geometry), and generated in sim mode.

## 7) Where Data Is Stored (Real + Sim)

- Persistent store: SQLite at `svc/data/audit.db`.
- Tables:
  - sensor metadata: `sensors`
  - time-series readings: `sensor_readings`
- Write path: sensor worker threads call `insert_sensor_reading(...)` for every emitted metric in both real and sim modes.
- Read path:
  - live latest: `/metrics/latest`
  - graph history: `/metrics/history`
  - logs tab source: `/logs/sensors`
  - CSV export: `/logs/sensors/export` (generated on-demand for download; not permanently stored as CSV by the backend).
- Extra file output:
  - JETI file-mode sim writes `.cap` files under the configured output path (typically `svc/data/jeti_sim_output`), then watcher ingestion writes those measurements into SQLite.
