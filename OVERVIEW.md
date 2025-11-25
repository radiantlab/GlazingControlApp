# SETUP AND MAP

## Project overview

Simple goal  
Control tint levels for 18 facade panels and 2 skylights in the OSU trailer  

Stack  
- FastAPI service in Python  
- React web app in TypeScript  
- Runs locally on a laptop today  
- Swap base URL to talk to the real trailer API later

---

## File map and what each file does

### Root

- **README.md** – Top-level summary and team list  
- **OVERVIEW.md** – This file; map of folders and what each file is for  
- **DEV-SETUP.md** – How to get Python + Node running and start both services  
- **LICENSE** – Project license  
- **CONTRIBUTING.md** – Branch rules, PR expectations, commit style, and CI notes  
- **.gitignore** – Keeps build output, local env files, venvs, and caches out of git  
- **.github/PULL_REQUEST_TEMPLATE.md** – PR checklist and sections to fill out  
- **.github/workflows/ci.yml** – Very simple CI that runs on push/PR (currently just echo / placeholder)  
- **docs/meeting_template.md** – Skeleton for meeting notes and action items  
- **docs/quick_start_draft.md** – Draft quick-start for researchers (how to use the app at a high level)  

---

## Service folder (`svc`)

Python FastAPI backend that simulates panels today and can talk to a real trailer API later.

- **svc/main.py**  
  - Creates the FastAPI app  
  - Mounts all routes from `app.routes`  
  - Enables CORS for the web app on port `5173`  

- **svc/requirements.txt**  
  - Python dependencies for the service (FastAPI, uvicorn, Pydantic, etc.)

- **svc/.env.example**  
  - Example env file to copy to `.env`  
  - Holds things like mode (`SIM` vs `REAL`), file paths for snapshot/audit logs, and any API keys / base URLs

- **svc/app/__init__.py**  
  - Empty marker so Python treats `app` as a package

- **svc/app/config.py**  
  - Central config object  
  - Reads environment variables (mode, snapshot path, audit log path, dwell timings, real API base URL, etc.)  
  - Used by `service.py`, `state.py`, and anything that needs config

- **svc/app/models.py**  
  - Pydantic models for:  
    - **Panel** – id, name, group id, level, last change time  
    - **Group** – id, name, member IDs  
    - **Commands** – request/response shapes for `/commands/set-level`  
    - **Snapshot** – current set of panels/groups  
    - **AuditLogEntry** – one line per command (time, actor, target, level, applied_to, result)

- **svc/app/state.py**  
  - Low-level persistence helpers  
  - Load and save snapshot JSON (panels + groups)  
  - Bootstraps default panels and groups when no state file exists  
  - Appends a single audit log JSON line per change to the audit log file  

- **svc/app/simulator.py**  
  - In-memory simulator for the whole system  
  - Applies level changes to facade panels and skylights  
  - Enforces simple rules for min/max and updates `last_change_ts`  
  - Writes updated snapshot via `state.py` so the state survives restarts  

- **svc/app/service.py**  
  - Core business logic layer  
  - Fronts the simulator in “sim” mode and can later be swapped to real trailer calls  
  - Enforces dwell time and any safety rules for level changes  
  - Writes audit entries for each successful or failed command  
  - Exposes functions used by `routes.py` for:  
    - Listing panels and groups  
    - Creating/updating/deleting groups  
    - Applying commands to a panel or group

- **svc/app/routes.py**  
  - All FastAPI route handlers:  
    - `GET /health` – status + current mode (`sim` / `real`)  
    - `GET /panels` – list all panels with current levels  
    - `GET /groups` – list all groups  
    - `POST /groups` – create group  
    - `PATCH /groups/{group_id}` – update group  
    - `DELETE /groups/{group_id}` – delete group  
    - `POST /commands/set-level` – set tint for a panel or group; returns which panels were actually touched and a human-readable message  
    - `GET /logs/audit` – paged list of `AuditLogEntry` rows for the Logs UI  

- **svc/tests/test_basic.py**  
  - Sanity tests for core behaviors:  
    - Health endpoint returns expected shape  
    - Panels/groups listing works  
    - Dwell time / repeated commands behave correctly  
    - Group updates/results look sane  

---

## Web folder (`web`)

React + Vite front-end with an HMI-style control screen.

### Top-level web files

- **web/index.html**  
  - Root HTML shell for the React app

- **web/package.json**  
  - NPM scripts (`dev`, `build`, `preview`)  
  - React, TypeScript, Vite, and other dependencies

- **web/tsconfig.json**  
  - TypeScript config: JSX/React, strictness, and Vite type support

- **web/vite.config.ts**  
  - Vite dev server config (port `5173`)  
  - Handles React plugin and env prefix for `VITE_*` variables

- **web/.env.development**  
  - Points the web app at the Python service:  
    - `VITE_API_BASE=http://127.0.0.1:8000` (or whatever you’re running)

- **web/src/env.d.ts**  
  - Type definitions for `import.meta.env` so TS knows about `VITE_API_BASE`, etc.

### Web entry + app shell

- **web/src/main.tsx**  
  - React entrypoint  
  - Mounts the app into `#root`  
  - Wraps everything in the `ToastProvider` so `useToast()` works everywhere

- **web/src/App.tsx**  
  - Initial UI for controlling the panels
  - Not currently being used

- **web/src/AppHMI.tsx**  
  - Main UI for controlling the panels  
  - Responsibilities:  
    - Fetch health, panels, groups via `api.ts` or `mockApi`  
    - Auto-refresh panel/group state on a timer  
    - Show system header (status, panel count, Clear All button, Logs, Manage)  
    - Manage group-level controls (select group, set numeric level or quick presets)  
    - Decide between full `RoomGrid` vs `RoomGridCompact` when the side panel is open  
    - Open/close the Manage side panel  
    - Open/close the Logs modal  
    - Use `controlManager` to coordinate manual, group, and routine control sources  
    - Show toasts for success/warning/error states

### API and mocking

- **web/src/api.ts**  
  - Typed client for talking to the FastAPI service  
  - Exposes:  
    - `health()`  
    - `panels()`  
    - `groups()`  
    - `createGroup`, `updateGroup`, `deleteGroup`  
    - `setPanelLevel`, `setGroupLevel` via `/commands/set-level`  
    - `auditLogs(limit)` for `GET /logs/audit`  
  - Centralized error handling and JSON parsing

- **web/src/mockData.ts**  
  - In-browser mock implementation mirroring `api.ts`  
  - Used when the backend is down or in “demo” mode  
  - Serves fake panels, groups, and health for quick UI development  
  - No real audit logs (Logs UI shows a “not available in mock mode” message)

### Components – HMI layout

- **web/src/components/RoomGrid.tsx**  
  - Main “room” layout for the full view  
  - Groups panels into sections and renders a grid of interactive tiles  
  - Each tile shows:  
    - Panel name + id  
    - Current tint level + last-change timestamp  
    - Slider for level  
    - Quick-set buttons (0/25/50/75/100)  
    - Apply button which calls back into `AppHMI` to set the panel level  
  - Visually indicates when a panel is transitioning and who controls it (manual/group/routine)

- **web/src/components/RoomGridCompact.tsx**  
  - Condensed overview grid used when the Manage side panel is open  
  - Each panel is a small square/rectangle with:  
    - Panel id  
    - Current level (with tint background)  
    - Small indicator for manual/group/routine control source  
  - Good for tracking the whole trailer at a glance while editing groups/routines

- **web/src/components/SidePanel.tsx**  
  - Right-hand slide-in “Manage” panel  
  - Tabs that mirror the HMI style tab bar  
  - Group management:  
    - List existing groups with their members  
    - Form to create/update groups (name + member IDs)  
    - Delete group action with confirm  
  - Future-proofed section for routines or other advanced controls  
  - Uses shared form styles so it feels like the same HMI as the main grid

- **web/src/components/ActiveControllersBar.tsx**  
  - Sticky bar at the very top of the app  
  - Shows all active routines and group controllers coming from `controlManager`  
  - Each chip: controller type, name, and count of panels it controls  
  - “Cancel” button for each item to release that control

- **web/src/components/LogsPanel.tsx**  
  - Centered modal dialog for logs (not a side panel)  
  - Stays a fixed max size in the middle of the screen  
  - Tabs styled to match the Manage side panel tabs:  
    - **Audit log** – table of command history  
    - **Sensor log** – placeholder for future sensor telemetry  
  - Props:  
    - `isOpen` / `onClose`  
    - `auditLogs`, `loading`, `error`  
    - `onRefresh` (manual refresh button)  
    - `isMock` (shows warning when logs are not available)  
  - Features:  
    - Filters by type (panel/group), target id, and result text  
    - Sortable columns (time, actor, type, target, level) with ▲/▼ indicator  
    - Nicely styled pills for target type, truncated “applied_to” and result columns  
  - `AppHMI` can also trigger auto-refresh polling while this modal is open

- **(Optional / legacy) web/src/components/PanelGrid.tsx**  
  - Earlier/alternative panel grid implementation  
  - Kept around as a simpler reference layout; the HMI now uses `RoomGrid`/`RoomGridCompact` instead

### Utilities

- **web/src/utils/controlManager.ts**  
  - Central authority for “who controls which panel right now”  
  - Tracks sources like:  
    - `manual` (single panel knob twist)  
    - `group` (group-wide commands)  
    - `routine` (future scheduled/automatic behaviors)  
  - Exposes methods:  
    - `getActiveControllers()` – returns a snapshot used by `ActiveControllersBar` and grids  
    - `getControlSource(panelId)` – who owns a specific panel  
    - `takeControl(source, forceOverride?)` – claim panels for a source, returning any conflicts  
    - `releaseControl(source)` – release control for that source  
    - `subscribe(listener)` – React-friendly subscription; `AppHMI` hooks this into state  
  - Used by `AppHMI` to:  
    - Allow manual override when needed  
    - Prompt user before overriding routines or groups  
    - Automatically release control after a transition completes

- **web/src/utils/toast.tsx**  
  - Simple toast notification system  
  - `<ToastProvider>` wraps the app; `useToast()` hook exposes `showToast(message, type)`  
  - Used for success, warning, and error messages (commands, API failures, etc.)  
  - All toasts share the same HMI-style look as the rest of the UI

### Styles

- **web/src/styles-hmi.css**  
  - Main styling for the HMI:  
    - Color tokens for background, surface, borders, text, and accent colors  
    - Layout for header, active controllers bar, room sections, panel tiles, and compact grid  
    - Slider styling, quick buttons, and apply buttons  
    - Side panel styling (Manage) including tabs, forms, and lists  
    - Toast styling for notifications  
    - Logs modal styling (centered `logs-modal` with tabs and table)  
  - Also contains responsive tweaks for narrow screens

- **web/src/styles.css** (if still present)  
  - Older/global styles; can be trimmed down as the app fully transitions to `styles-hmi.css`  

---

