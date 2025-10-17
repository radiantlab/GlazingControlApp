from __future__ import annotations
from typing import List
from .models import Panel, Group, TintLevel

class RealAdapter:
    """
    Placeholder for the real trailer integration.
    Implement these methods once the local API is validated.
    """
    def list_panels(self) -> List[Panel]:
        raise NotImplementedError("real adapter not implemented yet")

    def list_groups(self) -> List[Group]:
        raise NotImplementedError("real adapter not implemented yet")

    def set_panel(self, panel_id: str, level: TintLevel, min_dwell: int) -> bool:
        raise NotImplementedError("real adapter not implemented yet")

    def set_group(self, group_id: str, level: TintLevel, min_dwell: int) -> List[str]:
        raise NotImplementedError("real adapter not implemented yet")
