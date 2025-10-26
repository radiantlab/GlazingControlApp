# Simulator and Halio API Implementation

## Overview

The electrochromic glazing control system now supports seamless switching between a development simulator and real Halio hardware. This document explains the architecture, implementation, and how to use both modes.

## Architecture

```
Application Layer (routes.py, UI)
         ↓
   ControlService (service.py)
   - Stable interface
   - Mode switching logic
         ↓
    ┌────┴────┐
Simulator   RealAdapter
 (simple)   (Halio API)
```

### Design Philosophy

**Separation of Concerns:**
- **Simulator** = Fast, simple, predictable for development
- **RealAdapter** = Complete Halio API implementation
- **ControlService** = Translation layer that provides a stable interface

This architecture ensures:
1. **Zero application code changes** when switching modes
2. **Fast development** with the simulator
3. **Production-ready** Halio integration
4. **Easy testing** of each component independently

## Implementation Details

### 1. Simulator Enhancements

**File:** `svc/app/simulator.py`

**Changes:**
- Added 2-second transition time simulation
- Realistic behavior to catch timing issues during development
- Still uses simple panel IDs (P01, P02, etc.)
- Maintains persistent state across restarts

```python
def set_panel(self, panel_id: str, level: TintLevel, min_dwell: int) -> bool:
    # ... validation ...
    
    # Simulate realistic transition time (2 seconds)
    time.sleep(2.0)
    
    # Update state
    p.level = int(level)
    p.last_change_ts = time.time()
    save_snapshot(self.snap)
    return True
```

### 2. Halio API Integration

**File:** `svc/app/adapter.py`

**Complete RealAdapter implementation:**

**Features:**
- Full Halio API integration using requests library
- UUID-based window/group management
- Automatic panel ID → window UUID translation
- Handles Halio's async tinting (202 Accepted)
- Local dwell time enforcement
- State caching for performance
- Comprehensive error handling and logging

**Key Methods:**
- `list_panels()` - Fetches all windows, converts to Panel objects
- `list_groups()` - Fetches all groups with member mapping
- `set_panel()` - Tints a single window via Halio API
- `set_group()` - Tints a group via Halio API
- `_get_window_state()` - Queries live tint data
- `_can_change()` - Enforces local dwell time

**API Endpoints Used:**
- `GET /sites/{siteId}/windows` - List all windows
- `GET /sites/{siteId}/groups` - List all groups
- `GET /sites/{siteId}/windows/{windowId}/live-tint-data` - Get window state
- `POST /sites/{siteId}/windows/{windowId}/tint` - Tint a window
- `POST /sites/{siteId}/groups/{groupId}/tint` - Tint a group

### 3. Configuration System

**File:** `svc/app/config.py`

**New Environment Variables:**
```python
HALIO_API_URL = os.getenv("HALIO_API_URL", "https://api.halio.com")
HALIO_SITE_ID = os.getenv("HALIO_SITE_ID", "")
HALIO_API_KEY = os.getenv("HALIO_API_KEY", "")
WINDOW_MAPPING_FILE = os.path.join("svc", DATA_DIR, "window_mapping.json")
```

### 4. Panel to Window Mapping

**File:** `svc/svc/data/window_mapping.json`

Maps your internal panel IDs to Halio window UUIDs:

```json
{
  "P01": "abc-def-123-456-789",
  "P02": "abc-def-123-456-790",
  "SK1": "abc-def-123-456-791",
  ...
}
```

**How it works:**
1. RealAdapter loads this file on initialization
2. When you call `set_panel("P01", 50)`, it translates to the UUID
3. Makes Halio API call with the actual UUID
4. Response is translated back to your panel ID

## Usage Guide

### Simulator Mode (Development)

**Quick Start:**
```bash
cd svc
export SVC_MODE=sim
python3 main.py
```

**Use Cases:**
- Local development without hardware
- Fast iteration on features
- Testing control logic
- CI/CD testing

**Benefits:**
- No network calls
- Instant feedback (With assumed 2s transition time)
- No credentials needed
- Persistent state for debugging

### Real Hardware Mode (Production)

**Setup Steps:**

1. **Get Halio Credentials:**
   - Log into Halio account
   - Generate an API key
   - Note Site UUID

2. **Configure Environment:**
   ```bash
   export SVC_MODE=real
   export HALIO_API_URL=https://api.halio.com
   export HALIO_SITE_ID=your-actual-site-uuid
   export HALIO_API_KEY=your-actual-api-key
   ```

3. **Create Window Mapping:**
   - Query Halio API for window UUIDs
   - Update `svc/svc/data/window_mapping.json` with actual UUIDs
   - Map each panel ID (P01-P20, SK1-SK2) to its Halio window UUID

4. **Start Service:**
   ```bash
   cd svc
   python3 main.py
   ```

**Verification:**
- Check logs for "RealAdapter initialized"
- Verify window mapping count matches panels
- Test with a safe tint command
- Monitor Halio dashboard for changes

## Testing

**Run Tests:**
```bash
cd svc
python3 -m pytest tests/test_basic.py -v
```

**Test Coverage:**
- Health check with mode verification
- Panel/group listing
- Tint commands with dwell time enforcement
- State persistence
- Group tinting

**Note:** Tests run in simulator mode by default. The `test_set_and_dwell` test now takes ~2 seconds due to realistic transition simulation.

## Troubleshooting

### Simulator Mode

**Issue:** Tests are slow
- **Cause:** 2-second transition simulation
- **Solution:** This is intentional for realistic behavior

**Issue:** State persists between runs
- **Cause:** `svc/data/panels.json` stores state
- **Solution:** Delete file to reset, or modify manually

### Real Mode

**Issue:** "requests library required"
- **Solution:** `pip install requests` (included in requirements.txt)

**Issue:** "HALIO_API_KEY and HALIO_SITE_ID must be set"
- **Solution:** Set environment variables with actual credentials

**Issue:** "Panel X not mapped to Halio window UUID"
- **Solution:** Update `window_mapping.json` with actual UUIDs

**Issue:** Network timeouts
- **Check:** Network connectivity to Halio API
- **Check:** API credentials are valid
- **Check:** Site UUID is correct

**Issue:** 404 Not Found
- **Check:** Window UUIDs in mapping file are correct
- **Check:** Site ID matches your actual site
- **Query:** Halio API to verify window/group IDs

## Migration Path

### From Simulator to Real Hardware

1. **Develop and test in simulator mode** ✓
2. **Get Halio credentials** from account
3. **Query Halio for window UUIDs:**
   ```bash
   curl -H "Authorization: Bearer $HALIO_API_KEY" \
     https://api.halio.com/sites/$HALIO_SITE_ID/windows
   ```
4. **Map UUIDs** in `window_mapping.json`
5. **Set environment variables** for real mode
6. **Test with single panel** first
7. **Gradually test groups** and all panels
8. **Monitor logs and Halio dashboard**

### Zero-Downtime Switching

The architecture supports instant mode switching:
- Same application code
- Same API endpoints
- Same panel IDs
- Only backend changes

## Best Practices

1. **Always develop in simulator mode first**
2. **Test thoroughly before switching to real mode**
3. **Keep window mapping backed up**
4. **Monitor logs in production**
5. **Use environment variables, not hardcoded values**
6. **Validate credentials before deploying**
7. **Test with safe tint levels first (50%)**

## API Compatibility

### Your Application Interface

Unchanged - same endpoints:
- `GET /panels` - List all panels
- `GET /groups` - List all groups
- `POST /commands/set-level` - Set tint level
- `GET /health` - Check service status

### Halio API Coverage

Implemented:
- Window listing
- Group listing
- Single window tinting
- Group tinting
- Live tint data queries

Not yet implemented (future):
- Scenes
- Schedules/Automations
- Mode executions

## Future Enhancements

Potential additions:
1. **Async simulator** - Non-blocking transitions
2. **Halio webhooks** - Real-time updates
3. **Scene support** - Pre-configured patterns
4. **Schedule management** - Time-based control
5. **Error recovery** - Automatic retries
6. **Metrics collection** - Performance monitoring

## Summary

The implementation provides:
- Simple, fast simulator for development
- Complete Halio API integration
- Seamless mode switching
- Zero application code changes
- Production-ready architecture
- Comprehensive error handling
- Clear documentation and examples


