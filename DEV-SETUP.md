
## What you need to install
**Git** – Get it from [https://git-scm.com](https://git-scm.com)  
Check installation:
	git --version


**Python 3.11 or newer** – Get it from [https://python.org](https://python.org)  
On Windows, check “Add Python to PATH”.  
Check installation:
	python --version


**Node.js (LTS) and NPM** – Get it from [https://nodejs.org](https://nodejs.org)  
Check installation:
	node --version
	npm --version

---

## Repository setup
Clone the repository and go inside
	cd GlazingControlApp

---

## Run the service
Open a terminal in the `svc` folder:
`cd svc`


Create and activate a virtual environment:
- **Windows PowerShell**
	python -m venv .venv						
	..venv\Scripts\Activate.ps1

- **Windows CMD**
	.venv\Scripts\activate
	
- **Mac/Linux**					
	python3 -m venv .venv
	source .venv/bin/activate


Install packages:
	pip install --upgrade pip
	pip install -r requirements.txt


Create your `.env` file from the example:
- **Windows**		
	copy .env.example .env

- **Mac/Linux**
	cp .env.example .env


Start the server:
	python main.py

You should see Uvicorn running on port 8000.

Open the API docs in a browser: http://127.0.0.1:8000/docs

---

## Run the web app
Open a new terminal in the `web` folder:
	cd web


Install packages:
	npm install


Start the dev server:
	npm run dev


Open the link shown by Vite (usually http://127.0.0.1:5173).  
You should see the control interface.

Use the app:  
- The header shows service status  
- Pick a group, set a level, press **Set group**  
- Move a slider on any panel and press **Apply**  
- Press **Refresh** in the header to reload state  
