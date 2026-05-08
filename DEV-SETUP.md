# What you need to install

1. `Git`  
Get it from `https://git-scm.com`  
Check installation  
```bash
git --version
```

2. `Python >=3.11,<3.14`  
Get it from `https://python.org`  
On Windows check `Add Python to PATH`  
Check installation  
```bash
python --version
```
The backend declares this in `svc/pyproject.toml`. The repo-local `svc/.python-version` is for tools that read it.

3. `UV` (Recommended package manager)  
Get it from `https://github.com/astral-sh/uv`  
Installation (one-liner):
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```
Or use pip: `pip install uv`  
Or use homebrew: `brew install uv`  
Check installation  
```bash
uv --version
```

4. `Node.js (LTS) and NPM`  
Get it from `https://nodejs.org`  
Check installation  
```bash
node --version
npm --version
```

---

# Repository setup

1. Clone the repository and go inside  
```bash
cd GlazingControlApp
```

---

# Run the service

## Using UV (Recommended)

1. Open a terminal in the `svc` folder  
```bash
cd svc
```

2. Install dependencies and sync virtual environment  
UV will automatically create and manage a virtual environment:
```bash
uv sync
```

3. Create your `.env` file from the example

3.1 Windows  
```cmd
copy .env.example .env
```

3.2 Mac/Linux  
```bash
cp .env.example .env
```

4. Start the server  
```bash
uv run python main.py
```
Or activate the virtual environment first:
```bash
source .venv/bin/activate  # Mac/Linux
# or
.venv\Scripts\activate  # Windows
python main.py
```

You should see Uvicorn running on port 8000

Open the API docs in a browser at `http://127.0.0.1:8000/docs`

### Start the backend in real mode on Windows PowerShell

Use this on the site computer after `svc/data/sensors_config.json` has the real sensor values:

```powershell
cd svc
$env:SVC_MODE = "real"
uv sync
uv run python main.py
```

For the EKO C-BOX, set `eko_ms90_plus[].host` to the C-BOX IP address, usually `192.168.2.20`, and `eko_ms90_plus[].port` to TCP port `502`. The app no longer uses a USB-to-RS485 adapter or COM port for EKO.

---

## Using pip and venv (Legacy)

If you prefer to use pip and venv instead of UV:

1. Open a terminal in the `svc` folder  
```bash
cd svc
```

2. Create and activate a virtual environment

2.1 Windows PowerShell  
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

2.2 Windows CMD  
```cmd
.venv\Scripts\activate
```

2.3 Mac Linux  
```bash
python3 -m venv .venv
source .venv/bin/activate
```

3. Install packages  
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

4. Create your `.env` file from the example

4.1 Windows  
```cmd
copy .env.example .env
```

4.2 Mac Linux  
```bash
cp .env.example .env
```

5. Start the server  
```bash
python main.py
```

You should see Uvicorn running on port 8000

Open the API docs in a browser at `http://127.0.0.1:8000/docs`

---

# Run the web app

1. Open a new terminal in the `web` folder  
```bash
cd web
```

2. Install packages  
```bash
npm install
```

3. Start the dev server  
```bash
npm run dev
```

Open the link shown by Vite usually `http://127.0.0.1:5173`  
You should see the control interface

## Frontend build and checks

```bash
cd web
npm run typecheck
npm test
npm run build
```

Windows PowerShell uses the same commands.

---

# Use the app

1. The header shows service status  
2. Pick a group set a level press `Tint Group`  
3. Move a slider on any panel and press `Apply`  
4. Press `Refresh` in the header to reload state

## Verify live sensors

After the backend is running:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/sensors
Invoke-RestMethod http://127.0.0.1:8000/metrics/latest
```

Then open the HMI and verify the sensor cards, live graphs, and `Logs -> Sensor log`.

For EKO on site:

1. Open the C-BOX web UI from the site computer, usually `http://192.168.2.20/`.
2. Confirm the live readings page updates.
3. Open `Modbus -> Setup`.
4. Confirm Modbus TCP access is enabled.

## Troubleshooting

- `uv: command not found`: install uv, then open a new terminal and run `uv --version`.
- Wrong Python version: install Python 3.11, 3.12, or 3.13 and run `uv python pin 3.13` from `svc` if needed.
- Missing Python packages: run `cd svc` then `uv sync`. For pip/venv, rerun `pip install -r requirements.txt`.
- `npm: command not found`: install Node.js LTS and open a new terminal.
- Frontend dependency issues: run `cd web`, delete `node_modules` if needed, then `npm install`.
- Backend port already in use: stop the other process using port `8000`, or run `uv run uvicorn main:app --host 0.0.0.0 --port 8001`.
- C-BOX web UI unreachable: confirm the site computer is on the C-BOX network, verify the IP address, and check Ethernet cabling/firewall rules.
- EKO Modbus read failures: confirm C-BOX Modbus TCP is enabled and TCP `502` is reachable.
- `GET /sensors` is empty in real mode: check `SVC_MODE=real`, `SENSORS_CONFIG_FILE`, and required sensor config fields. Real mode does not create simulated sensors as fallback.

---

# Build a Podman Image and Deploy It

To build a new image:

```sh
podman build -t glazing-control-app .
```

To run the container in podman:

```sh
podman run --rm -p 8000:8000 `
    -v "${PWD}\svc\data:/app/svc/data" `
    -e SVC_MODE=real `
    -e HALIO_API_URL= `
    -e HALIO_SITE_ID= `
    -e HALIO_API_KEY= `
    glazing-control-app
```
