from __future__ import annotations
import asyncio
import os
import time
import subprocess
import threading
from typing import Dict, Any

from app.state import (
    save_routine, 
    get_routine, 
    update_routine_status, 
    delete_routine, 
    list_routines
)

# Global dictionary to track active routine processes and their buffered logs
# { "routine_id": {"process": Popen, "logs": [str], "task": asyncio.Task | None} }
active_routines: Dict[str, Dict[str, Any]] = {}

ROUTINES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "data", "routines")

PREAMBLE = """
import requests
import time
import sys
import math

API_URL = "http://127.0.0.1:8000"

def log(*args):
    print(*args)
    sys.stdout.flush()

class SensorsWrapper:
    def get_latest(self, sensor_id: str, metric: str):
        try:
            r = requests.get(f"{API_URL}/metrics/latest")
            r.raise_for_status()
            data = r.json()
            for d in data:
                if d.get("sensor_id") == sensor_id and d.get("metric") == metric:
                    return d.get("value")
            return None
        except Exception as e:
            log(f"Error fetching sensor data: {e}")
            return None
            
    def list(self):
        try:
            r = requests.get(f"{API_URL}/sensors")
            return r.json()
        except:
            return []

class PanelsWrapper:
    def list(self):
        try:
            r = requests.get(f"{API_URL}/panels")
            return r.json()
        except:
            return []
            
    def set_level(self, panel_id: str, level: int):
        try:
            r = requests.post(
                f"{API_URL}/commands/set-level",
                json={"target_type": "panel", "target_id": panel_id, "level": int(level), "actor": "routine"}
            )
            log(f"✓ Panel {panel_id} -> {level}%")
            return r.json()
        except Exception as e:
            log(f"Error setting panel level: {e}")
            return None

class GroupsWrapper:
    def list(self):
        try:
            r = requests.get(f"{API_URL}/groups")
            return r.json()
        except:
            return []
            
    def set_level(self, group_id: str, level: int):
        try:
            r = requests.post(
                f"{API_URL}/commands/set-level",
                json={"target_type": "group", "target_id": group_id, "level": int(level), "actor": "routine"}
            )
            log(f"✓ Group {group_id} -> {level}%")
            return r.json()
        except Exception as e:
            log(f"Error setting group level: {e}")
            return None

sensors = SensorsWrapper()
panels = PanelsWrapper()
groups = GroupsWrapper()

# --- BEGIN USER CODE ---
"""


def _ensure_routines_dir():
    os.makedirs(ROUTINES_DIR, exist_ok=True)


def _log_reader(process: subprocess.Popen, routine_id: str):
    """Background thread to read stdout from the subprocess and append to the buffer."""
    if routine_id not in active_routines:
        return
        
    try:
        if process.stdout:
            for line in iter(process.stdout.readline, ''):
                if not line:
                    break
                # Only keep the last 500 lines to prevent memory leaks
                logs = active_routines[routine_id]["logs"]
                logs.append(line.rstrip())
                if len(logs) > 500:
                    active_routines[routine_id]["logs"] = logs[-500:]
    except ValueError:
        pass # Handle closed file gracefully

    process.wait()
    
    # Process ended
    if routine_id in active_routines:
        code = process.returncode
        if code == 0:
            active_routines[routine_id]["logs"].append(f"✅ Route finished cleanly.")
            update_routine_status(routine_id, "done")
        elif code == -15 or code == 15: # SIGTERM
            pass # We manually killed it, handled in stop_routine
        else:
            active_routines[routine_id]["logs"].append(f"❌ Routine crashed with exit code {code}.")
            update_routine_status(routine_id, "error")


def _execute_subprocess(routine_id: str, code: str, mode: str, interval_ms: int | None, indefinite: bool):
    _ensure_routines_dir()
    script_path = os.path.join(ROUTINES_DIR, f"{routine_id}.py")
    
    # Build the script content
    script_content = PREAMBLE + "\n"
    
    if mode == "once":
        script_content += code
    elif mode == "interval":
        interval_secs = (interval_ms or 5000) / 1000.0
        script_content += f"import time\n"
        if indefinite:
            script_content += f"while True:\n"
        else:
            # Run for max 1 hour (3600 seconds)
            script_content += f"start_time = time.time()\n"
            script_content += f"while time.time() - start_time < 3600:\n"
            
        # Indent the user's code inside the loop
        for line in code.split("\n"):
            script_content += f"    {line}\n"
        script_content += f"    time.sleep({interval_secs})\n"

    # Write script to disk
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script_content)

    # Spawn process using python3 (or uv run python if needed, but python3 usually works inside venv contexts)
    process = subprocess.Popen(
        ["python3", script_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )

    active_routines[routine_id] = {
        "process": process,
        "logs": ["▶ Running routine..."],
        "task": active_routines.get(routine_id, {}).get("task")
    }
    
    update_routine_status(routine_id, "running")

    # Start reader thread
    t = threading.Thread(target=_log_reader, args=(process, routine_id), daemon=True)
    t.start()


async def _scheduled_execution(routine_id: str, delay_seconds: float, code: str, mode: str, interval_ms: int | None, indefinite: bool):
    """Asyncio task to wait the required delay before executing the subprocess."""
    try:
        await asyncio.sleep(delay_seconds)
        if routine_id in active_routines:
            _execute_subprocess(routine_id, code, mode, interval_ms, indefinite)
    except asyncio.CancelledError:
        pass


def start_routine(
    routine_id: str,
    name: str,
    code: str,
    mode: str,
    interval_ms: int | None,
    run_at_ts: float | None,
    indefinite: bool
) -> None:
    
    delay_s = 0.0
    initial_status = "running"
    
    if run_at_ts:
        delay_s = run_at_ts - time.time()
        if delay_s > 0:
            initial_status = "scheduled"
        else:
            delay_s = 0.0
            
    save_routine(routine_id, name, code, mode, interval_ms, run_at_ts, indefinite, initial_status)
    
    if delay_s > 0:
        active_routines[routine_id] = {
            "process": None,
            "logs": [f"⏳ Scheduled to start at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(run_at_ts))}"],
            "task": None
        }
        
        task = asyncio.create_task(_scheduled_execution(routine_id, delay_s, code, mode, interval_ms, indefinite))
        active_routines[routine_id]["task"] = task
    else:
        _execute_subprocess(routine_id, code, mode, interval_ms, indefinite)


def stop_routine(routine_id: str) -> None:
    """Terminates the subprocess or cancels the scheduled task."""
    if routine_id in active_routines:
        r = active_routines[routine_id]
        if r.get("task"):
            r["task"].cancel()
        if r.get("process"):
            r["process"].terminate()
            
        r["logs"].append("⏹ Routine stopped")
        del active_routines[routine_id]
        
    update_routine_status(routine_id, "stopped")


def remove_routine(routine_id: str) -> None:
    """Stops the routine and deletes it from the database."""
    stop_routine(routine_id)
    delete_routine(routine_id)


def resume_routines() -> None:
    """Called at startup to resume routines from SQLite that should still be running or scheduled."""
    routines = list_routines()
    for r in routines:
        status = r["status"]
        if status in ["running", "scheduled"]:
            # Recalculate if it should be scheduled or run now
            start_routine(
                routine_id=r["id"],
                name=r["name"],
                code=r["code"],
                mode=r["mode"],
                interval_ms=r.get("interval_ms"),
                run_at_ts=r.get("run_at_ts"),
                indefinite=r["indefinite"]
            )
