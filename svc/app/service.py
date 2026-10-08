from __future__ import annotations
import logging
from typing import List, Tuple
from .models import TintLevel
from .simulator import Simulator
from .adapter import HalioAdapter
from .config import ENVIRONMENT, Environment, MIN_DWELL_SECONDS
from .state import audit, update_panel_state

logger = logging.getLogger(__name__)


class ControlService:
    def __init__(self) -> None:
        self.environment = ENVIRONMENT
        if self.environment is Environment.PRODUCTION:
            self.backend = HalioAdapter()
        else:
            self.backend = Simulator()

    # read
    def list_panels(self):
        return self.backend.list_panels()

    def list_groups(self):
        return self.backend.list_groups()

    # write
    def set_panel_level(
        self, panel_id: str, level: TintLevel, actor: str = "api"
    ) -> Tuple[bool, List[str], str]:
        logger.info(
            f"Service.set_panel_level called: panel={panel_id} level={level} "
            f"environment={self.environment.value} actor={actor}"
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

    def create_group(self, name: str, member_ids: List[str]):
        if self.environment is not Environment.DEVELOPMENT:
            raise RuntimeError("group create is available only in development")
        return self.backend.create_group(name, member_ids)

    def update_group(self, group_id: str, name: str | None, member_ids: List[str] | None):
        if self.environment is not Environment.DEVELOPMENT:
            raise RuntimeError("group update is available only in development")
        return self.backend.update_group(group_id, name, member_ids)

    def delete_group(self, group_id: str) -> bool:
        if self.environment is not Environment.DEVELOPMENT:
            raise RuntimeError("group delete is available only in development")
        return self.backend.delete_group(group_id)
