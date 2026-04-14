# On-Site Sensor Checklist

Use this at the trailer/lab PC after the hardware is physically installed.

## Connection Order

1. Connect each `T-10A` head chain to its T-10A body.
2. If a T-10A body has multiple heads, connect external power to that setup.
3. Connect each `T-10A` body to the PC by USB.
4. Connect each JETI device to the PC by USB.
5. If the JETI path will use file mode, confirm the PC software is configured to write a live `.cap` file or folder.
6. If the JETI path will use direct serial mode, confirm the JETI USB driver is installed and a COM port appears in Windows.
7. Connect the EKO `MS-90` and optional `MS-80S` to the `C-BOX`.
8. Connect `C-BOX` output power and RS-485 wiring.
9. Connect the USB-to-RS485 adapter from the `C-BOX` output side to the PC.

## Windows Checks

1. Open Device Manager.
2. Record the COM port for each `T-10A` body.
3. Record the COM port for each JETI device that will use direct serial mode.
4. Record the COM port for the USB-RS485 adapter used by the `C-BOX`.
5. If a JETI device is missing, install the JETI USB driver and reconnect it.

## Update `svc/data/sensors_config.json`

1. Set `t10a[].port` to the actual T-10A COM port.
2. Set `t10a[].heads[].head_no` to the actual physical T-10A adaptor/head ID.
3. Set `jeti_spectraval[].transport` to either `file` or `serial_scpi`.
4. If JETI uses file mode, set `jeti_spectraval[].output_path` to the actual live `.cap` file or folder.
5. If JETI uses serial mode, set `jeti_spectraval[].port` to the JETI COM port.
6. If JETI uses serial mode, set `jeti_spectraval[].baudrate`:
   - `921600` for `spectraval 1511`
   - `115200` for `specbos 1211-2`
7. Set `eko_ms90_plus[].port` to the COM port of the USB-RS485 adapter.

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

For the full step-by-step connection instructions for each sensor and each supported method, use [`docs/real_sensor_setup.md`](./real_sensor_setup.md).

## If Something Fails

- No T-10A data:
  - re-check USB COM port
  - verify head IDs
  - verify straight CAT5 and external power for multi-point mode
- No JETI data:
  - re-check driver install
  - confirm the PC measurement software is writing to the configured `output_path`, or
  - confirm COM port and baudrate for serial mode
- No EKO data:
  - swap RS-485 `A/B`
  - verify `12 VDC` power and fuse
  - verify `slave_address`
  - try a different `float_byte_order` if values are present but incorrect
