# What you need to install

1. `Git`  
Get it from `https://git-scm.com`  
Check installation  
```bash
git --version
```

2. `Python 3.11 or newer`  
Get it from `https://python.org`  
On Windows check `Add Python to PATH`  
Check installation  
```bash
python --version
```

3. `Node.js (LTS) and NPM`  
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

---

# Use the app

1. The header shows service status  
2. Pick a group set a level press `Set group`  
3. Move a slider on any panel and press `Apply`  
4. Press `Refresh` in the header to reload state
