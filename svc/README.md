# Control service

What this gives you today
- Lists panels and groups
- Sets tint level for a single panel or a group
- Enforces dwell time per panel
- Writes an audit log to `svc/data/audit.json`
- Simulator by default and a stub for real hardware

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
