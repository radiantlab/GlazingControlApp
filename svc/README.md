# Control service

What this gives you today
- Lists panels and groups
- Sets tint level for a single panel or a group
- Enforces dwell time per panel
- Writes an audit log to SQLite database `svc/data/audit.db`
- Simulator for development (default)
- Halio API integration for real hardware

## Setup

Python 3.11 or newer

### Using UV (Recommended)

```bash
cd svc
uv sync
uv run python main.py
```

UV automatically creates and manages a virtual environment. You can also activate it manually:
```bash
source .venv/bin/activate  # macOS/Linux
# or
. .venv\Scripts\activate  # Windows
python main.py
```

### Using pip and venv (Legacy)

```bash
cd svc
python -m venv .venv
# Windows
. .venv/Scripts/activate
# macOS or Linux
# source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

## Configuration

The service operates in two modes:

### Simulator Mode (Default)

For development and testing without hardware. Uses simple panel IDs (P01, P02, etc.).

```bash
export SVC_MODE=sim
export SVC_MIN_DWELL_SECONDS=20
python main.py
```

Features:
- Fast iteration without real hardware
- Persistent state across restarts
- 2-second simulated transition time (Until real time is discovered)
- Simple panel/group management

### Real Hardware Mode (Halio API)

For production use with actual electrochromic panels via Halio API.

```bash
export SVC_MODE=real
export HALIO_API_URL=https://api.halio.com
export HALIO_SITE_ID=site-uuid
export HALIO_API_KEY=api-key
export SVC_MIN_DWELL_SECONDS=20
python main.py
```

**Required Setup:**

1. **Get Halio credentials** from Halio account
2. **Configure window mapping** in `svc/data/window_mapping.json`:
   ```json
   {
     "P01": "actual-halio-window-uuid-1",
     "P02": "actual-halio-window-uuid-2",
     ...
   }
   ```
3. **Install requests library** (included in requirements.txt)

The adapter automatically:
- Translates panel IDs to Halio window UUIDs
- Handles Halio's async tinting (202 Accepted responses)
- Manages site/window/group architecture
- Enforces dwell times locally
- Caches window states for performance

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SVC_MODE` | `sim` | Mode: `sim` or `real` |
| `SVC_MIN_DWELL_SECONDS` | `20` | Minimum seconds between tint changes |
| `SVC_DATA_DIR` | `data` | Directory for state/log database and config files |
| `HALIO_API_URL` | - | Halio API base URL (real mode only) |
| `HALIO_SITE_ID` | - | Your Halio site UUID (real mode only) |
| `HALIO_API_KEY` | - | Your Halio API key (real mode only) |
| `SENSORS_CONFIG_FILE` | `svc/data/sensors_config.json` | Sensor runtime config. If you override it, prefer an absolute path. |
| `SVC_ENABLE_T10A_IN_SIM` | `false` | Enable T-10A polling in sim mode |
| `SVC_ENABLE_JETI_SERIAL_IN_SIM` | `false` | Enable JETI serial polling in sim mode |
| `SVC_ENABLE_EKO_IN_SIM` | `false` | Enable EKO C-BOX polling in sim mode |

### Sensor Integration (Real Mode)

The backend supports three real sensor paths via `svc/data/sensors_config.json`:

- `t10a`: Konica Minolta T-10A via USB virtual COM (9600, 7E1)
- `jeti_spectraval`: one or more JETI devices (`spectraval 1511` or `specbos 1211-2`) via either
  - `transport: "file"` (watch a live `.cap` file or folder written by the PC measurement workflow), or
  - `transport: "serial_scpi"` (direct SPECFIRM serial)
- `eko_ms90_plus`: EKO C-BOX over Modbus RTU (RS-485, default 9600, 8N1, slave 1)

See the sample config in [`svc/data/sensors_config.json`](./data/sensors_config.json) and
the detailed runbook in [`docs/real_sensor_setup.md`](../docs/real_sensor_setup.md).

For a shorter field checklist, use [`docs/on_site_sensor_checklist.md`](../docs/on_site_sensor_checklist.md).

### Sensor Integration (Sim Mode)

In `SVC_MODE=sim`, the backend now emits live sample data for all three sensor families:

- `t10a`: simulated lux for each configured head
- `jeti_spectraval`: existing `.cap` sim writer + watcher flow
- `eko_ms90_plus`: simulated irradiance/solar-position/temperature telemetry

This means the HMI can render:

- live latest values per sensor
- one live graph per sensor with metric selection
- live sensor logs with CSV export

without physical hardware attached.

If you need to poll real serial devices while still in sim mode, set:

- `SVC_ENABLE_T10A_IN_SIM=true`
- `SVC_ENABLE_JETI_SERIAL_IN_SIM=true`
- `SVC_ENABLE_EKO_IN_SIM=true`

### Sensor Log APIs

The following endpoints are available in both `sim` and `real` modes:

- `GET /logs/sensors`:
  returns sensor reading log rows with filters (`sensor_id`, `metric`, `ts_from`, `ts_to`) and sorting.
- `GET /logs/sensors/export`:
  exports filtered sensor logs as CSV.

Existing sensor metric APIs remain:

- `GET /sensors`
- `GET /metrics/latest`
- `GET /metrics/history`

## Testing

Run tests with:
```bash
uv run pytest tests/
```

Or with pip/venv:
```bash
pytest tests/
```

Tests run in simulator mode by default
