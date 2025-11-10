from __future__ import annotations
import json
import os
import time
import logging
from typing import List, Dict, Optional
from .models import Panel, Group, TintLevel
from .config import HALIO_API_URL, HALIO_SITE_ID, HALIO_API_KEY, WINDOW_MAPPING_FILE

# Try to import requests, but fail gracefully if not available
try:
    import requests

    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

logger = logging.getLogger(__name__)


class RealAdapter:
    """
    Halio API integration for real panel control.

    This adapter translates between our simple panel interface and the
    Halio API's UUID-based architecture with sites, windows, groups, and drivers.
    """

    def __init__(self) -> None:
        if not HAS_REQUESTS:
            raise ImportError(
                "requests library required for real mode. "
                "Install with: pip install requests"
            )

        if not HALIO_API_KEY or not HALIO_SITE_ID:
            raise ValueError(
                "HALIO_API_KEY and HALIO_SITE_ID must be set in environment "
                "for real mode operation"
            )

        self.base_url = HALIO_API_URL
        self.site_id = HALIO_SITE_ID
        self.headers = {
            "Authorization": f"Bearer {HALIO_API_KEY}",
            "Content-Type": "application/json",
        }

        # Load panel ID to Halio window UUID mapping
        self.panel_to_window: Dict[str, str] = self._load_window_mapping()
        self.window_to_panel: Dict[str, str] = {
            v: k for k, v in self.panel_to_window.items()
        }

        # Cache for window states to enforce dwell time
        self._state_cache: Dict[str, Dict] = {}

        logger.info(f"RealAdapter initialized for site {self.site_id}")
        logger.info(f"Loaded {len(self.panel_to_window)} panel mappings")

    def _load_window_mapping(self) -> Dict[str, str]:
        """
        Load mapping from panel IDs (P01, P02, etc.) to Halio window UUIDs.

        The mapping file should be JSON format:
        {
            "P01": "uuid-for-window-1",
            "P02": "uuid-for-window-2",
            ...
        }
        """
        if not os.path.exists(WINDOW_MAPPING_FILE):
            logger.warning(
                f"Window mapping file not found: {WINDOW_MAPPING_FILE}. "
                "Creating empty mapping. You must populate this file with actual UUIDs."
            )
            return {}

        try:
            with open(WINDOW_MAPPING_FILE, "r", encoding="utf-8") as f:
                mapping = json.load(f)
            # Filter out comment keys (starting with '_')
            return {k: v for k, v in mapping.items() if not k.startswith("_")}
        except Exception as e:
            logger.error(f"Failed to load window mapping: {e}")
            return {}

    def _get_window_state(self, window_id: str) -> Optional[Dict]:
        """Query current state of a window from Halio API."""
        try:
            url = f"{self.base_url}/sites/{self.site_id}/windows/{window_id}/live-tint-data"
            response = requests.get(url, headers=self.headers, timeout=10)

            if response.status_code == 200:
                data = response.json()
                self._state_cache[window_id] = {
                    "current_tint": data.get("currentTint", 0),
                    "last_updated": time.time(),
                }
                return self._state_cache[window_id]
            elif response.status_code == 404:
                logger.error(f"Window {window_id} not found")
                return None
            else:
                logger.error(f"Failed to get window state: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Error querying window state: {e}")
            return None

    def _can_change(self, window_id: str, min_dwell: int) -> bool:
        """Check if enough time has passed since last change."""
        if window_id not in self._state_cache:
            # Fetch current state
            self._get_window_state(window_id)

        if window_id in self._state_cache:
            last_update = self._state_cache[window_id].get("last_updated", 0)
            return (time.time() - last_update) >= min_dwell

        # If we can't determine, allow the change
        return True

    def list_panels(self) -> List[Panel]:
        """
        Fetch all windows from Halio API and convert to Panel objects.
        """
        try:
            # Option 1: Get all windows for the site
            url = f"{self.base_url}/sites/{self.site_id}/windows"
            response = requests.get(url, headers=self.headers, timeout=10)

            if response.status_code != 200:
                logger.error(f"Failed to list windows: {response.status_code}")
                return []

            windows = response.json()
            panels = []

            for window in windows:
                window_id = window.get("id")
                panel_id = self.window_to_panel.get(window_id, window_id)

                # Get live tint data for each window
                state = self._get_window_state(window_id)
                current_tint = state.get("current_tint", 0) if state else 0

                panel = Panel(
                    id=panel_id,
                    name=window.get("name", f"Window {panel_id}"),
                    level=current_tint,
                    last_change_ts=state.get("last_updated", 0) if state else 0,
                )
                panels.append(panel)

            return panels

        except Exception as e:
            logger.error(f"Error listing panels: {e}")
            return []

    def list_groups(self) -> List[Group]:
        """
        Fetch all groups from Halio API and convert to Group objects.
        """
        try:
            url = f"{self.base_url}/sites/{self.site_id}/groups"
            response = requests.get(url, headers=self.headers, timeout=10)

            if response.status_code != 200:
                logger.error(f"Failed to list groups: {response.status_code}")
                return []

            halio_groups = response.json()
            groups = []

            for hg in halio_groups:
                group_id = hg.get("id")
                # Get member windows and convert to panel IDs
                member_window_ids = hg.get("members", [])
                member_panel_ids = [
                    self.window_to_panel.get(wid, wid) for wid in member_window_ids
                ]

                group = Group(
                    id=group_id,
                    name=hg.get("name", f"Group {group_id}"),
                    member_ids=member_panel_ids,
                )
                groups.append(group)

            return groups

        except Exception as e:
            logger.error(f"Error listing groups: {e}")
            return []

    def set_panel(self, panel_id: str, level: TintLevel, min_dwell: int) -> bool:
        """
        Set tint level for a single panel via Halio API.

        Returns True if command accepted, False if dwell time not met or error.
        """
        # Translate panel ID to window UUID
        window_id = self.panel_to_window.get(panel_id)
        if not window_id:
            logger.error(f"Panel {panel_id} not found in window mapping")
            raise KeyError(f"Panel {panel_id} not mapped to Halio window UUID")

        # Check dwell time
        if not self._can_change(window_id, min_dwell):
            logger.info(f"Dwell time not met for panel {panel_id}")
            return False

        try:
            # POST to Halio API
            url = f"{self.base_url}/sites/{self.site_id}/windows/{window_id}/tint"
            payload = {"tintLevel": int(level)}

            response = requests.post(
                url, headers=self.headers, json=payload, timeout=10
            )

            # Halio returns 202 Accepted for async commands
            if response.status_code == 202:
                logger.info(
                    f"Tint command accepted for panel {panel_id} → level {level}"
                )
                # Update cache
                self._state_cache[window_id] = {
                    "current_tint": int(level),
                    "last_updated": time.time(),
                }
                return True
            elif response.status_code == 404:
                logger.error(f"Window {window_id} not found")
                raise KeyError(f"Window {window_id} not found on Halio")
            elif response.status_code == 400:
                logger.error(f"Invalid tint command: {response.text}")
                return False
            else:
                logger.error(
                    f"Halio API error: {response.status_code} - {response.text}"
                )
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error setting panel {panel_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error setting panel {panel_id}: {e}")
            return False

    def set_group(self, group_id: str, level: TintLevel, min_dwell: int) -> List[str]:
        """
        Set tint level for a group via Halio API.

        Returns list of panel IDs that were successfully updated.
        """
        try:
            # Halio supports group tinting directly
            url = f"{self.base_url}/sites/{self.site_id}/groups/{group_id}/tint"
            payload = {"tintLevel": int(level)}

            response = requests.post(
                url, headers=self.headers, json=payload, timeout=10
            )

            if response.status_code == 202:
                # Get group members
                groups = self.list_groups()
                for g in groups:
                    if g.id == group_id:
                        logger.info(
                            f"Tint command accepted for group {group_id} → level {level}"
                        )
                        # Update cache for all members
                        for panel_id in g.member_ids:
                            window_id = self.panel_to_window.get(panel_id)
                            if window_id:
                                self._state_cache[window_id] = {
                                    "current_tint": int(level),
                                    "last_updated": time.time(),
                                }
                        return g.member_ids
                return []
            elif response.status_code == 404:
                logger.error(f"Group {group_id} not found")
                raise KeyError(f"Group {group_id} not found on Halio")
            else:
                logger.error(
                    f"Halio API error: {response.status_code} - {response.text}"
                )
                return []

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error setting group {group_id}: {e}")
            return []
        except KeyError:
            raise
        except Exception as e:
            logger.error(f"Error setting group {group_id}: {e}")
            return []
