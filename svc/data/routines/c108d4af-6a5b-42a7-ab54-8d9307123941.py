
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

import time
while True:
    all_panels = panels.list()
    for p in all_panels:
        panels.set_level(p["id"], 0)
    log("All panels cleared to 0%")
    time.sleep(10000.0)
