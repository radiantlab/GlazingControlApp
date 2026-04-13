# On-Site Sensor Checklist

Use this at the trailer/lab PC after the hardware is physically installed.

## Before Powering The App

- Confirm each `T-10A` body is connected to the PC by USB.
- Confirm every `T-10A` head/adaptor chain uses straight CAT5.
- Confirm T-10A multi-head setups have external power.
- Confirm each JETI device is connected to the PC by USB.
- Confirm the EKO `C-BOX` has:
  - `12 VDC` power
  - USB-to-RS485 adapter connected
  - `A/B` wired to the adapter
- Confirm LiVal or SPECFIRM is installed if the JETI path depends on it.

## Windows Checks

1. Open Device Manager.
2. Record COM ports for:
   - each `T-10A`
   - each `JETI`
   - the USB-RS485 adapter used by the `C-BOX`
3. If a JETI device is missing, install the JETI USB drivers and reconnect it.

## Update `svc/data/sensors_config.json`

- `t10a[].port` -> actual T-10A COM port
- `t10a[].heads[].head_no` -> actual physical T-10A adaptor/head ID
- `jeti_spectraval[].transport` -> `file` or `serial_scpi`
- `jeti_spectraval[].output_path` -> LiVal `.cap` file/folder if using file mode
- `jeti_spectraval[].port` -> actual JETI COM port if using serial mode
- `jeti_spectraval[].baudrate`
  - `921600` for `spectraval 1511`
  - `115200` for `specbos 1211-2`
- `eko_ms90_plus[].port` -> COM port of the USB-RS485 adapter

## Start The Backend

```powershell
cd svc
$env:SVC_MODE = "real"
uv run python main.py
```

Use `SENSORS_CONFIG_FILE` only if you are not using the default `svc/data/sensors_config.json`.

## Acceptance Checks

```powershell
Invoke-RestMethod http://127.0.0.1:8000/sensors
Invoke-RestMethod http://127.0.0.1:8000/metrics/latest
```

Verify:

- T-10A sensors report `lux`
- JETI sensors report `lux` plus color/spectral metrics
- EKO reports `ghi_w_m2`, `dni_w_m2`, `dhi_w_m2`, and sun position data

Then open the HMI and confirm:

- live sensor cards are populated
- live graphs update
- `Logs -> Sensor log` is filling with new rows
- sensor CSV export works

## If Something Fails

- No T-10A data:
  - re-check USB COM port
  - verify head IDs
  - verify straight CAT5 and external power for multi-point mode
- No JETI data:
  - re-check driver install
  - confirm LiVal is writing to the configured `output_path`, or
  - confirm COM port and baudrate for serial mode
- No EKO data:
  - swap RS-485 `A/B`
  - verify `12 VDC` power and fuse
  - verify `slave_address`
  - try a different `float_byte_order` if values are present but incorrect
