# Real Sensor Setup

This runbook is for the trailer/lab PC when the app is running in `SVC_MODE=real`.

The current real-mode implementation supports the hardware shown in the current wiring diagram and sensor manuals:

- Konica Minolta `T-10A` illuminance meters over USB/virtual COM
- JETI `spectraval 1511` and `specbos 1211-2` over either:
  - LiVal `.cap` file export, or
  - direct SPECFIRM serial/virtual COM
- EKO `MS-90+` system through the `C-BOX` Modbus RTU output

## 1) Topology From The Site Schematic

The latest site diagram shows three distinct PC-facing paths:

- `T-10A`:
  - receptor heads connect to the body through the Konica Minolta adapter/head chain and straight CAT5 cabling
  - the body connects to the local PC by USB
- `JETI spectraval/specbos`:
  - the instrument connects directly to the local PC by USB
  - LiVal/SPECFIRM can expose the device as a live `.cap` writer or a virtual COM port
- `EKO MS-90+`:
  - the MS-90 DNI sensor and optional MS-80S feed the `C-BOX`
  - the PC talks only to the `C-BOX` output side over RS-485 Modbus RTU

That matches the backend architecture now:

- `T10AClient` polls the T-10A serial link and emits `lux`
- `JetiSpecfirmClient` polls SPECFIRM directly and now parses wavelength/value ASCII pairs correctly
- `JetiSpectravalFileWatcher` ingests LiVal `.cap` output and now handles the watched file/folder appearing after the service starts
- `EkoCBoxModbusClient` polls C-BOX holding registers for irradiance, sun position, GPS, and temperature

## 2) Before You Go On Site

Bring or confirm access to:

- the local trailer/lab PC
- all required USB cables for each `T-10A` body and each `JETI` instrument
- `T-A20`, `T-A21`, and `AC-A412` if the T-10A heads are being used in multi-point mode
- straight CAT5 patch cables for T-10A head/adaptor runs
- a USB-to-RS485 adapter for the EKO `C-BOX`
- a stable `12 VDC` supply for the `C-BOX` output cable
- a `120 ohm` termination resistor if the RS-485 run needs end termination
- JETI Windows drivers and LiVal/SPECFIRM access on the local PC

## 3) Configure The App

The default runtime config file is:

- `svc/data/sensors_config.json`

You do not need to set `SENSORS_CONFIG_FILE` if you use that default file.

If you do use a custom file, prefer an absolute path. The service also resolves common relative paths now, but absolute paths are still the least ambiguous choice on site.

### Recommended startup from `svc/`

```powershell
cd svc
$env:SVC_MODE = "real"
uv run python main.py
```

### If you must use a custom sensor config file

```powershell
cd svc
$env:SVC_MODE = "real"
$env:SENSORS_CONFIG_FILE = "C:\path\to\sensors_config.json"
uv run python main.py
```

## 4) T-10A Setup

### Physical setup

1. Connect the `T-10A` body to the local PC by USB.
2. Connect each receptor head through the required T-10A head adapters.
3. Use straight CAT5/10Base-T patch cables only.
4. If you are doing multi-point measurement, use the external `AC-A412` power supply.
5. Assign unique head/adaptor IDs. The T-10A manual allows IDs `00` through `29`.

### What to check on the PC

1. Open Windows Device Manager.
2. Look under `Ports (COM & LPT)`.
3. Record the COM port used by each T-10A body.

### Config fields

In `t10a`:

- `port`: COM port for the body, for example `COM3`
- `heads[].head_no`: the configured head/adaptor ID used by that body
- `heads[].sensor_id`: app-facing sensor ID, for example `T10A1-H1`
- `heads[].label`: human readable name shown in the UI

### T-10A watch-outs

- Do not use crossover Ethernet cables between adapters and heads.
- Multi-head mode needs external power.
- If the configured head numbers do not match the physical adapter IDs, the service will poll the wrong head or get no data.
- USB COM assignments can move if you plug the body into a different USB port on the PC.

## 5) JETI Setup

The app supports both `spectraval 1511` and `specbos 1211-2`.

Use one config entry per physical JETI device.

### Option A: LiVal `.cap` file export

Use this when LiVal is already part of the operator workflow.

#### Physical/software setup

1. Install the JETI USB drivers first if the PC does not already have them.
2. Connect the device to the PC by USB.
3. In LiVal, configure continuous saving/export to a known `.cap` file or folder.
4. Make sure the app `output_path` points to that same file or folder.

#### Config fields

In `jeti_spectraval`:

- `transport: "file"`
- `output_path`: path to the live `.cap` file or the folder that will receive rotating `.cap` files
- `watch_interval_s`: how often the backend checks for new data

#### File-mode watch-outs

- The backend can now recover if LiVal creates the file or folder after the service starts.
- The path still has to match exactly. If LiVal writes to a different folder, the app will stay empty.
- File mode is the safest option when operators already use LiVal for acquisition.

### Option B: Direct SPECFIRM serial polling

Use this when you want the backend to talk to the JETI device directly with no LiVal file export step.

#### Physical setup

1. Install the JETI USB drivers if needed.
2. Connect the device to the PC by USB.
3. Find the COM port in Device Manager.

#### Config fields

In `jeti_spectraval`:

- `transport: "serial_scpi"`
- `port`: COM port
- `baudrate`: optional, but verify it
  - `spectraval 1511`: `921600`
  - `specbos 1211-2`: `115200`
- `tint_ms`: integration time in milliseconds
- `avg_count`: measurement averaging count

#### Direct-serial watch-outs

- The driver now parses SPECFIRM format `2` correctly as `wavelength<TAB>value` pairs. That fix is required for valid real metrics.
- If you use a `specbos` device and omit `baudrate`, the service now defaults it to `115200`.
- If serial polling fails immediately, verify the COM port and baudrate before changing anything else.

## 6) EKO MS-90+ / C-BOX Setup

The PC talks to the `C-BOX`, not directly to the `MS-90` or `MS-80S`.

### C-BOX output-side wiring to the PC

Per the C-BOX manual output cable:

1. `Brown` -> `+12 V` supply
2. `White` -> supply ground / `0 V`
3. `Blue` -> Modbus `A` / `+`
4. `Black` -> Modbus `B` / `-`
5. `Grey` -> not connected

Use a `0.5 A` fuse on the supply as recommended by the manual.

At the end of the RS-485 run, add a `120 ohm` termination resistor across `A/B` if your topology needs termination.

### C-BOX sensor-side terminals

Per the EKO C-BOX manual:

- `MS-80S`
  - terminal `3`: white / `0 V`
  - terminal `4`: brown / `12 VDC out`
  - terminal `5`: black / Modbus `B`
  - terminal `6`: blue / Modbus `A`
  - terminal `7`: grey / Modbus ground
- `MS-90`
  - terminal `11`: brown / DNI `+`
  - terminal `12`: white / DNI `-`
  - terminal `15`: blue / `12 VDC out`
  - terminal `16`: black / `0 VDC out`

### Config fields

In `eko_ms90_plus`:

- `port`: COM port of the USB-RS485 adapter
- `baudrate`: usually `9600`
- `slave_address`: usually `1`
- `float_byte_order`: default `ABCD`

### EKO watch-outs

- If you get no Modbus response, `A/B` may be swapped on the USB-RS485 adapter labeling. Swap the pair and test again.
- If values are present but obviously wrong, try `float_byte_order` values in this order:
  - `ABCD`
  - `CDAB`
  - `BADC`
  - `DCBA`
- The C-BOX will expose `DHI` only when the MS-90/MS-80S system is wired and operating as expected.

## 7) What To Verify On The Local PC

After wiring and config:

1. Start the backend in `real` mode.
2. Confirm the service sees all configured sensors:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/sensors
```

3. Confirm live metrics are arriving:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/metrics/latest
```

4. Open the HMI in the browser and verify:
   - every sensor card shows current values
   - every sensor graph updates
   - `Logs -> Sensor log` fills with new rows
5. Export a CSV from the sensor log tab and confirm it contains:
   - timestamp
   - sensor ID
   - sensor kind
   - sensor label
   - metric
   - value

## 8) Expected Real Metrics

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

Sensor metadata and time-series readings are stored in:

- `svc/data/audit.db`

Relevant tables:

- `sensors`
- `sensor_readings`

The UI reads that data through:

- `GET /sensors`
- `GET /metrics/latest`
- `GET /metrics/history`
- `GET /logs/sensors`
- `GET /logs/sensors/export`
