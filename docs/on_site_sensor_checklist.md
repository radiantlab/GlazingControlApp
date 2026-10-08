# On-Site Sensor Checklist

Use this at the trailer/lab PC after the hardware is physically installed.

## Connection Order

1. Connect each `T-10A` head chain to its T-10A body.
2. If a T-10A body has multiple heads, connect external power to that setup.
3. Connect each `T-10A` body to the PC by USB.
4. Connect each JETI device to the PC by USB.
5. If the JETI path will use file mode, confirm LiVal is writing a live
   line-oriented capture file and record its exact Windows path.
6. If the JETI path will use direct serial mode, confirm the JETI USB driver is installed and a COM port appears in Windows.
7. Connect the EKO `MS-90` and optional `MS-80S` to the `C-BOX`.
8. Connect the `C-BOX` Ethernet port to the site computer/network.
9. Confirm the `C-BOX` is powered and its web UI shows live EKO readings.

## Windows Checks

1. Open Device Manager.
2. Run `.\scripts\sensors\Start-SensorAgent.ps1 -Command list-ports`. It
   lists ports without opening them. Record the USB `serial_number` (and `vid`,
   `pid`) for each `T-10A` body.
3. Record the same identity for each JETI device that will use direct serial
   mode.
4. If a JETI device is missing, install the JETI USB driver and reconnect it.
5. Open the C-BOX web UI from the site computer: `http://192.168.40.50/`.
6. In the C-BOX web UI, open `Modbus -> Setup` and confirm Modbus TCP access is enabled.

## Update the production `sensors_config.json`

1. For each connected T-10A body in the template (`KM1`, `KM2`), set
   `"enabled": true`, keep `"port": "auto"` and `"acquisition": "external"`,
   and replace the placeholder `port_identity.serial_number` with the recorded
   USB serial. Do not hard-code COM numbers; they change when USB devices
   reconnect.
2. Set `t10a[].heads[].head_no` to the actual physical T-10A adaptor/head ID.
3. Set `jeti_spectraval[].transport` to either `file` or `serial_scpi`.
4. If JETI uses file mode, keep the template's
   `"input_path": "specbos-lival.capture"`. It resolves under
   `SVC_SENSOR_INPUT_DIR`, where Compose mounts the file named by
   `SVC_JETI_CAPTURE_PATH`.
   **REQUIREMENT**: When configuring multiple JETI sensors (Spectraval or Specbos) in file mode, you MUST configure the Jeti software to export each sensor's data to a distinct file name (e.g., `spectraval_1.cap`, `specbos.cap`). Do not point multiple sensors to the same file, as this will cause data collisions.
5. If JETI uses serial mode, set `"acquisition": "external"`,
   `"port": "auto"`, and `port_identity` to the recorded identity.
6. If JETI uses serial mode, set `jeti_spectraval[].baudrate`:
   - `921600` for `spectraval 1511`
   - `115200` for `specbos 1211-2`
7. Set `eko_ms90_plus[].host` to the C-BOX IP address, `192.168.40.50` in the
   trailer.
8. Set `eko_ms90_plus[].port` to TCP port `502`.
9. Keep `eko_ms90_plus[].slave_address` at `1` unless the C-BOX configuration says otherwise.
10. Keep `eko_ms90_plus[].float_byte_order` at `CDAB` from the template.

The file must come from the external directory selected by
`SVC_PRODUCTION_CONFIG_DIR`; it is mounted read-only in the container.

## Update `svc/.env.production`

1. Set `SVC_PRODUCTION_DATA_DIR`, `SVC_PRODUCTION_CONFIG_DIR`, and
   `SVC_DB_BACKUP_DIR` to existing absolute directories.
2. Set `SVC_JETI_CAPTURE_PATH` to the exact LiVal capture file. It must exist
   before the container starts.
3. If any device is marked `"acquisition": "external"` (any enabled T-10A, or
   JETI serial), set `SVC_SENSOR_INGEST_TOKEN` to a long random value. The API
   refuses to start without it while an enabled device is marked external.

## Start The Backend

```powershell
podman compose --env-file svc/.env.production up -d --build
```

`docker compose` takes the same arguments.

If any device is marked external, start the Sensor Agent on the Windows host:

```powershell
.\scripts\sensors\Start-SensorAgent.ps1 -Command once
.\scripts\sensors\Start-SensorAgent.ps1 -Command continuous
```

## Acceptance Checks

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
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

For the full step-by-step connection instructions for each sensor and each
supported method, use
[`docs/production_sensor_setup.md`](./production_sensor_setup.md). For the
production LiVal capture diagnosis and integration options, use
[`docs/jeti_lival_integration.md`](./jeti_lival_integration.md).

## If Something Fails

- No T-10A data:
  - re-run `list-ports` and confirm `port_identity` matches exactly one port
  - confirm the Sensor Agent is running and `SVC_SENSOR_INGEST_TOKEN` is set
  - verify head IDs
  - verify straight CAT5 and external power for multi-point mode
  - stop the Sensor Agent, then probe the port directly (9600 7E1, not 8N1):

```powershell
cd svc
uv run python scripts/read_t10a_serial.py COM5
```

  - you should see a 14-byte PC-mode reply; if RX is empty, another app may hold the port or the meter is off/not in USB PC mode
- No JETI data:
  - re-check driver install
  - confirm LiVal is writing to the file named by `SVC_JETI_CAPTURE_PATH`, or
  - confirm the active LiVal capture file rather than relying on
    `LastCapturePath` or `lival_session.log`
  - confirm `port_identity` and baudrate for serial mode
- No EKO data:
  - open the C-BOX web UI from the site computer and confirm it is reachable
  - confirm `Modbus -> Setup` has Modbus TCP access enabled
  - verify `host`, TCP `port`, and `slave_address` in the production `sensors_config.json`
  - confirm firewall/network rules allow TCP `502` to the C-BOX
  - confirm `float_byte_order` is `CDAB` if values are present but incorrect
