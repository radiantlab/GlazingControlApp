# Real Sensor Setup

This runbook is for the trailer/lab PC when the app is running in `SVC_MODE=real`.

The current real-mode implementation supports the hardware shown in the current wiring diagram and sensor manuals:

- Konica Minolta `T-10A` illuminance meters over USB/virtual COM
- JETI `spectraval 1511` and `specbos 1211-2` over either:
  - file-based `.cap` ingestion from the PC measurement workflow, or
  - direct SPECFIRM serial/virtual COM
- EKO `MS-90+` system through the `C-BOX` Modbus RTU output

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
  - the PC talks only to the `C-BOX` output side over RS-485 Modbus RTU
  - the app does not configure a separate DAC interface; the backend-facing link is still the `C-BOX` output path

That matches the backend architecture now:

- `T10AClient` polls the T-10A serial link and emits `lux`
- `JetiSpecfirmClient` polls SPECFIRM directly and now parses wavelength/value ASCII pairs correctly
- `JetiSpectravalFileWatcher` ingests file-based `.cap` output and now handles the watched file/folder appearing after the service starts
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
- JETI Windows drivers and either:
  - the PC software that will write the `.cap` output path, or
  - SPECFIRM access for direct serial polling

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

The app supports one practical connection path for `T-10A`: head chain to T-10A body, then body to PC by USB.

### Method A: Single-head T-10A to PC

1. Place the `T-10A` body near the local PC.
2. Connect the receptor head to the T-10A body using the correct Konica Minolta head/adaptor hardware.
3. If any CAT5 segment is used in the chain, use straight CAT5/10Base-T patch cable only.
4. Connect the T-10A body to the PC by USB.
5. Power on the T-10A body and confirm it is detected by Windows.
6. Open Device Manager and record the assigned COM port under `Ports (COM & LPT)`.
7. Update `svc/data/sensors_config.json`:
   - set `t10a[].port` to the actual COM port
   - set `heads[].head_no` to the physical head/adaptor ID
   - keep `heads[].sensor_id` and `heads[].label` aligned with the physical head location
8. Start the backend and confirm the T-10A sensor reports `lux`.

### Method B: Multi-head T-10A to PC

1. Place the `T-10A` body near the local PC.
2. Connect each receptor head through the required `T-A20` / `T-A21` adapter chain.
3. Use straight CAT5/10Base-T patch cable between the multi-point components.
4. Connect the `AC-A412` external power supply for the multi-head setup.
5. Assign a unique physical ID to each head/adaptor. The supported range is `00` through `29`.
6. Connect the T-10A body to the PC by USB.
7. Open Device Manager and record the COM port for that T-10A body.
8. Update `svc/data/sensors_config.json`:
   - set the device `port`
   - set each `heads[].head_no` to the actual physical ID
   - keep each `sensor_id` and `label` tied to the installed head location
9. Start the backend and verify every configured T-10A head appears in `GET /sensors`.
10. Confirm each head produces `lux` in `GET /metrics/latest`.

### T-10A watch-outs

- Do not use crossover Ethernet cables.
- Multi-head mode needs external power.
- If `head_no` does not match the physical head/adaptor ID, the service will poll the wrong head or no head.
- USB COM assignments can change if you move the USB cable to a different PC port.

## 5) JETI Setup

The app supports both `spectraval 1511` and `specbos 1211-2`.

There are two supported connection methods in the app: file-based ingestion and direct serial polling. The physical cable to the PC is USB in both cases.

### Method A: JETI over USB with file-based `.cap` ingestion

Use this when the measurement workflow on the PC writes JETI `.cap` output that the backend can watch.

1. Install the JETI USB driver on the local PC if it is not already installed.
2. Connect the JETI device to the PC by USB.
3. Open the JETI software on the PC and confirm the device is detected.
4. Configure the JETI software to save or export measurements to a known `.cap` file or to a folder that receives rotating `.cap` files.
5. Record the exact file path or folder path being written on the PC.
6. Update `svc/data/sensors_config.json`:
   - set `jeti_spectraval[].transport` to `"file"`
   - set `jeti_spectraval[].output_path` to that exact file or folder
   - set `watch_interval_s` if you want faster or slower pickup
7. Start the backend in real mode.
8. Trigger or wait for a fresh JETI measurement so the `.cap` output updates.
9. Confirm the app begins receiving JETI metrics in `GET /metrics/latest`.

### Method B: JETI over USB virtual COM with direct SPECFIRM polling

Use this when you want the backend to talk to the JETI device directly instead of reading exported files.

1. Install the JETI USB driver on the local PC if needed.
2. Connect the JETI device to the PC by USB.
3. Open Device Manager and find the JETI virtual COM port under `Ports (COM & LPT)`.
4. Record the COM port.
5. Decide which device model is connected:
   - `spectraval 1511` typically uses `921600`
   - `specbos 1211-2` typically uses `115200`
6. Update `svc/data/sensors_config.json`:
   - set `jeti_spectraval[].transport` to `"serial_scpi"`
   - set `jeti_spectraval[].port` to the JETI COM port
   - set `jeti_spectraval[].baudrate` to the correct device baud rate
   - set `tint_ms` and `avg_count` if the measurement timing needs adjustment
7. Start the backend in real mode.
8. Confirm the JETI sensor appears in `GET /sensors`.
9. Confirm the JETI sensor reports `lux` and spectral/color metrics in `GET /metrics/latest`.

### JETI watch-outs

- The schematic confirms USB to the PC. The file-vs-serial choice is a software integration choice, not a different physical cable path.
- File mode only works if the configured `output_path` exactly matches the real file or folder on the PC.
- The backend can now recover if the watched `.cap` file or folder appears after startup, but the path still has to be correct.
- Direct serial mode requires the correct COM port and baudrate before anything else will work.
- The backend now parses SPECFIRM format `2` correctly as `wavelength<TAB>value` pairs.

## 6) EKO MS-90+ / C-BOX Setup

The app supports one real connection path for EKO: the sensors wire into the `C-BOX`, and the PC talks only to the `C-BOX` output side over RS-485 through a USB adapter.

### Method A: MS-90 plus optional MS-80S into C-BOX, then C-BOX to PC

1. Mount the `C-BOX` where the EKO sensors can reach its terminals and where the PC-side output cable can reach the USB-to-RS485 adapter.
2. Wire the `MS-90` sensor into the `C-BOX` sensor-side terminals:
   - terminal `11`: brown / DNI `+`
   - terminal `12`: white / DNI `-`
   - terminal `15`: blue / `12 VDC out`
   - terminal `16`: black / `0 VDC out`
3. If `MS-80S` is installed, wire it into the `C-BOX` sensor-side terminals:
   - terminal `3`: white / `0 V`
   - terminal `4`: brown / `12 VDC out`
   - terminal `5`: black / Modbus `B`
   - terminal `6`: blue / Modbus `A`
   - terminal `7`: grey / Modbus ground
4. Wire the `C-BOX` output cable to its power supply and to the USB-to-RS485 adapter:
   - `Brown` -> `+12 V`
   - `White` -> `0 V / ground`
   - `Blue` -> Modbus `A / +`
   - `Black` -> Modbus `B / -`
   - `Grey` -> not connected
5. Use a `0.5 A` fuse on the `12 VDC` supply line.
6. If the RS-485 run is at the end of the bus and needs termination, add a `120 ohm` resistor across `A/B`.
7. Plug the USB-to-RS485 adapter into the local PC.
8. Open Device Manager and record the COM port for that USB-to-RS485 adapter.
9. Update `svc/data/sensors_config.json`:
   - set `eko_ms90_plus[].port` to the adapter COM port
   - confirm `baudrate` is usually `9600`
   - confirm `slave_address` is usually `1`
   - leave `float_byte_order` at `ABCD` unless testing shows otherwise
10. Start the backend in real mode.
11. Confirm the EKO sensor appears in `GET /sensors`.
12. Confirm `ghi_w_m2`, `dni_w_m2`, `dhi_w_m2`, and sun-position metrics appear in `GET /metrics/latest`.

### EKO watch-outs

- The PC does not connect directly to `MS-90` or `MS-80S`.
- If there is no Modbus response, swap RS-485 `A/B` at the adapter.
- If values are present but obviously wrong, try `float_byte_order` values in this order: `ABCD`, `CDAB`, `BADC`, `DCBA`.
- `DHI` depends on the MS-90/MS-80S system being wired and operating correctly through the C-BOX.

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
