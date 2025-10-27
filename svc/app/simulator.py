from __future__ import annotations
import time
import threading
from typing import Dict, List
from .models import Panel, Group, TintLevel, Snapshot
from .state import load_snapshot, save_snapshot

class Simulator:
    def __init__(self) -> None:
        # load from disk so levels persist across restarts
        self.snap: Snapshot = load_snapshot()
        # Track panels currently transitioning, api only responds with request received, not completed initially
        self._transitioning: Dict[str, threading.Thread] = {}
        if not self.snap.panels:
            # caller should have bootstrapped but keep safe
            pass

    def list_panels(self) -> List[Panel]:
        return list(self.snap.panels.values())

    def list_groups(self) -> List[Group]:
        return list(self.snap.groups.values())

    def _can_change(self, p: Panel, min_dwell: int) -> bool:
        return (time.time() - p.last_change_ts) >= min_dwell

    def set_panel(self, panel_id: str, level: TintLevel, min_dwell: int) -> bool:
        if panel_id not in self.snap.panels:
            raise KeyError(panel_id)
        p = self.snap.panels[panel_id]
        if not self._can_change(p, min_dwell):
            return False
        
        # Set a realistic transition time (Unconfirmed but works for development)
        time.sleep(2.0)
        
        p.level = int(level)
        p.last_change_ts = time.time()
        save_snapshot(self.snap)
        return True

    def set_group(self, group_id: str, level: TintLevel, min_dwell: int) -> List[str]:
        if group_id not in self.snap.groups:
            raise KeyError(group_id)
        applied: List[str] = []
        for pid in self.snap.groups[group_id].member_ids:
            ok = self.set_panel(pid, level, min_dwell)
            if ok:
                applied.append(pid)
        return applied
