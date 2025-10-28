# SETUP AND MAP

## Project overview
Simple goal  
Control tint levels for 18 facade panels and 2 skylights in the OSU trailer  
FastAPI service in Python  
React web app in TypeScript  
Runs on your laptop today  
Swap to the real trailer later

---

## File map and what each file does

### Root
* **README.md** – Top level summary and team list  
* **OVERVIEW.md** – General Overview of each file
* **DEV-SETUP.md** – Instructions for development setup 
* **LICENSE** – License  
* **CONTRIBUTING.md** – Rules for branches, reviews, commits, and CI  
* **.gitignore** – Keeps build output, local env, and cache out of git  
* **.github/PULL_REQUEST_TEMPLATE.md** – Pull request checklist and sections  
* **.github/workflows/ci.yml** -  CI that echoes a message on push and pull request  
* **docs/meeting_template.md** – Skeleton for meeting notes and action items  
* **docs/quick_start_draft.md** – Early draft for a researcher quick start  

### Service folder (svc)
* **svc/main.py** – Starts FastAPI, mounts routes, enables CORS for the web app on port 5173  
* **svc/requirements.txt** – Python packages used by the service  
* **svc/.env.example** – Sample settings to copy to .env  
* **svc/app/__init__.py** – Empty marker so Python treats app as a package  
* **svc/app/config.py** – Reads env settings, mode (sim or real), file paths for saved data and audit log  
* **svc/app/models.py** – Pydantic models for panels, groups, requests, and responses; snapshot and audit entry shapes  
* **svc/app/routes.py** – API endpoints for the web app (GET health, GET panels, GET groups, POST commands/set-level)  
* **svc/app/service.py** – Core logic layer; picks simulator in sim mode; enforces dwell time and writes audit  
* **svc/app/simulator.py** – In-memory simulator with disk persistence; updates panel levels and saves snapshot  
* **svc/app/state.py** – Load and save snapshot JSON; bootstrap default panels and groups; append one audit line per change  
* **svc/tests/test_basic.py** – Tests health listing, dwell, and group updates  

### Web folder (web)
* **web/index.html** – Root HTML for the React app  
* **web/package.json** – NPM scripts and dependencies  
* **web/tsconfig.json** – TypeScript config with React JSX and Vite types  
* **web/vite.config.ts** – Vite dev server config (port 5173)  
* **web/.env.development** – Points the web app to the service at http://127.0.0.1:8000  
* **web/src/env.d.ts** – Types for Vite env values  
* **web/src/main.tsx** – React entry and mount  
* **web/src/App.tsx** – Main page with status, group control, and panel grid  
* **web/src/api.ts** – Small client for health, panels, groups, and tint commands  
* **web/src/styles.css** – Theme layout for cards, sliders, chips, and header styling  
* **web/src/components/PanelGrid.tsx** – Cards for each panel with a slider, quick chips, and apply  
