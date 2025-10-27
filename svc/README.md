# Control service

What this gives you today
- Lists panels and groups
- Sets tint level for a single panel or a group
- Enforces dwell time per panel
- Writes an audit log to `svc/data/audit.json`
- Simulator for development (default)
- Halio API integration for real hardware

## Setup

Python 3.11 or newer

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
| `SVC_DATA_DIR` | `data` | Directory for state and audit files |
| `HALIO_API_URL` | - | Halio API base URL (real mode only) |
| `HALIO_SITE_ID` | - | Your Halio site UUID (real mode only) |
| `HALIO_API_KEY` | - | Your Halio API key (real mode only) |

## Testing

Run tests with:
```bash
pytest tests/
```

Tests run in simulator mode by default
