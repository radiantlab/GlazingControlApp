from __future__ import annotations
import logging
from typing import List, Tuple
from .models import Group, GroupLayout, TintLevel
from .simulator import Simulator
from .adapter import RealAdapter
from .config import MODE, MIN_DWELL_SECONDS
from .state import audit, load_groups, save_groups, update_panel_state

logger = logging.getLogger(__name__)


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
        groups = self.backend.list_groups()
        local_groups = load_groups()
        merged_groups: list[Group] = []
        for group in groups:
            local_group = local_groups.get(group.id)
            if local_group and local_group.layout is not None:
                merged_groups.append(group.model_copy(update={"layout": local_group.layout}))
            else:
                merged_groups.append(group)
        return merged_groups

    # write
    def set_panel_level(
        self, panel_id: str, level: TintLevel, actor: str = "api"
    ) -> Tuple[bool, List[str], str]:
        logger.info(
            f"Service.set_panel_level called: panel={panel_id} level={level} "
            f"mode={self.mode} actor={actor}"
        )
        try:
            ok = self.backend.set_panel(panel_id, level, MIN_DWELL_SECONDS)
            if ok:
                applied = [panel_id]
                msg = "panel updated"
                logger.info(f"✓ Panel {panel_id} update SUCCESS")
                # Update panel state in database when command is successful
                # This keeps displayed tint level accurate based on successful API responses
                try:
                    update_panel_state(panel_id, int(level))
                    logger.debug(f"Updated panel state for {panel_id} to level {level}")
                except Exception as e:
                    logger.warning(f"Failed to update panel state for {panel_id}: {e}")
            else:
                applied = []
                msg = "dwell time not met"
                logger.warning(f"⚠ Panel {panel_id} update FAILED: {msg}")
            audit(actor, "panel", panel_id, int(level), applied, msg)
            return ok, applied, msg
        except KeyError as e:
            logger.error(f"✗ Panel {panel_id} update FAILED: panel not found - {e}")
            return False, [], "panel not found"

    def set_group_level(
        self, group_id: str, level: TintLevel, actor: str = "api"
    ) -> Tuple[bool, List[str], str]:
        try:
            applied = self.backend.set_group(group_id, level, MIN_DWELL_SECONDS)
            ok = applied is not None
            applied_ids = applied or []
            msg = "group updated" if ok else "no panels updated due to dwell time"
            if ok:
                # Update panel states for all panels that were successfully updated
                for panel_id in applied_ids:
                    try:
                        update_panel_state(panel_id, int(level))
                        logger.debug(f"Updated panel state for {panel_id} to level {level}")
                    except Exception as e:
                        logger.warning(f"Failed to update panel state for {panel_id}: {e}")
            audit(actor, "group", group_id, int(level), applied_ids, msg)
            return ok, applied_ids, msg
        except KeyError:
            return False, [], "group not found"

    def create_group(self, name: str, member_ids: List[str], layout: GroupLayout | None = None):
        if not hasattr(self.backend, "create_group"):
            raise RuntimeError("group create not supported in this mode")
        group = self.backend.create_group(name, member_ids, layout)
        if self.mode == "real":
            local_groups = load_groups()
            local_groups[group.id] = group
            save_groups(local_groups)
        return group

    def update_group(
        self,
        group_id: str,
        name: str | None,
        member_ids: List[str] | None,
        layout: GroupLayout | None = None,
    ):
        if hasattr(self.backend, "update_group"):
            return self.backend.update_group(group_id, name, member_ids, layout)

        existing = next((group for group in self.backend.list_groups() if group.id == group_id), None)
        if existing is None:
            raise KeyError(group_id)

        if (name is not None and name != existing.name) or (
            member_ids is not None and list(member_ids) != list(existing.member_ids)
        ):
            raise RuntimeError("group membership/name updates not supported in this mode")

        updated = existing.model_copy(update={"layout": layout})
        local_groups = load_groups()
        local_groups[group_id] = updated
        save_groups(local_groups)
        return updated

    def delete_group(self, group_id: str) -> bool:
        if not hasattr(self.backend, "delete_group"):
            raise RuntimeError("group delete not supported in this mode")
        return self.backend.delete_group(group_id)
