from __future__ import annotations
from typing import List, Tuple
from .models import TintLevel
from .simulator import Simulator
from .adapter import RealAdapter
from .config import MODE, MIN_DWELL_SECONDS
from .state import audit

class ControlService:
    def __init__(self) -> None:
        self.mode = MODE
        if self.mode == "real":
            self.backend = RealAdapter()
        else:
            self.backend = Simulator()

    # read
    def list_panels(self):
        return self.backend.list_panels()

    def list_groups(self):
        return self.backend.list_groups()

    # write
    def set_panel_level(self, panel_id: str, level: TintLevel, actor: str = "api") -> Tuple[bool, List[str], str]:
        try:
            ok = self.backend.set_panel(panel_id, level, MIN_DWELL_SECONDS)
            if ok:
                applied = [panel_id]
                msg = "panel updated"
            else:
                applied = []
                msg = "dwell time not met"
            audit(actor, "panel", panel_id, int(level), applied, msg)
            return ok, applied, msg
        except KeyError:
            return False, [], "panel not found"

    def set_group_level(self, group_id: str, level: TintLevel, actor: str = "api") -> Tuple[bool, List[str], str]:
        try:
            applied = self.backend.set_group(group_id, level, MIN_DWELL_SECONDS)
            ok = len(applied) > 0
            msg = "group updated" if ok else "no panels updated due to dwell time"
            audit(actor, "group", group_id, int(level), applied, msg)
            return ok, applied, msg
        except KeyError:
            return False, [], "group not found"
