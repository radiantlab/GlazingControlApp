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
8. Connect the `C-BOX` Ethernet port to the site computer/network.
9. Confirm the `C-BOX` is powered and its web UI shows live EKO readings.

## Windows Checks

1. Open Device Manager.
2. Record the COM port for each `T-10A` body.
3. Record the COM port for each JETI device that will use direct serial mode.
4. If a JETI device is missing, install the JETI USB driver and reconnect it.
5. Open the C-BOX web UI from the site computer, usually `http://192.168.2.20/`.
6. In the C-BOX web UI, open `Modbus -> Setup` and confirm Modbus TCP access is enabled.

## Update `svc/data/sensors_config.json`

1. Set `t10a[].port` to the actual T-10A COM port.
2. Set `t10a[].heads[].head_no` to the actual physical T-10A adaptor/head ID.
3. Set `jeti_spectraval[].transport` to either `file` or `serial_scpi`.
4. If JETI uses file mode, set `jeti_spectraval[].output_path` to the actual live `.cap` file.
   **REQUIREMENT**: When configuring multiple JETI sensors (Spectraval or Specbos) in file mode, you MUST configure the Jeti software to export each sensor's data to a distinct file name (e.g., `spectraval_1.cap`, `specbos.cap`). Do not point multiple sensors to the same file, as this will cause data collisions.
5. If JETI uses serial mode, set `jeti_spectraval[].port` to the JETI COM port.
6. If JETI uses serial mode, set `jeti_spectraval[].baudrate`:
   - `921600` for `spectraval 1511`
   - `115200` for `specbos 1211-2`
7. Set `eko_ms90_plus[].host` to the C-BOX IP address, usually `192.168.2.20`.
8. Set `eko_ms90_plus[].port` to TCP port `502`.
9. Keep `eko_ms90_plus[].slave_address` at `1` unless the C-BOX configuration says otherwise.

## Start The Backend

```powershell
cd svc
$env:SVC_MODE = "real"
uv sync
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
  - stop the backend, then probe the port directly (9600 7E1, not 8N1):

```powershell
cd svc
uv run python scripts/read_t10a_serial.py COM5
```

  - you should see a 14-byte PC-mode reply; if RX is empty, another app may hold the port or the meter is off/not in USB PC mode
- No JETI data:
  - re-check driver install
  - confirm the PC measurement software is writing to the configured `output_path`, or
  - confirm COM port and baudrate for serial mode
- No EKO data:
  - open the C-BOX web UI from the site computer and confirm it is reachable
  - confirm `Modbus -> Setup` has Modbus TCP access enabled
  - verify `host`, TCP `port`, and `slave_address` in `svc/data/sensors_config.json`
  - confirm firewall/network rules allow TCP `502` to the C-BOX
  - try a different `float_byte_order` if values are present but incorrect
