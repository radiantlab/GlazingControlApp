from __future__ import annotations
import os
import time
import logging
from typing import Any, List, Dict, Optional
from .group_layout import normalize_group_layout
from .models import Panel, Group, GroupLayout, TintLevel
from .config import (
    HALIO_API_URL,
    HALIO_API_KEY,
    HALIO_SITE_ID,
)

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

        self.base_url = HALIO_API_URL.rstrip("/")
        self.site_id = HALIO_SITE_ID
        self.headers = {
            "X-API-Key": HALIO_API_KEY,
            "Content-Type": "application/json"
        }

        self.window_cache: Dict[str, Dict[str, Any]] = {}
        self._ensured_single_window_groups = False

        # Cache for window states to enforce dwell time
        self._state_cache: Dict[str, Dict] = {}

        logger.info(f"RealAdapter initialized for site {self.site_id}")
        logger.info(
            "Using Halio-discovered windows/groups without local window_mapping.json"
        )

    def _extract_results(self, response_data: Any) -> Any:
        if isinstance(response_data, dict) and "results" in response_data:
            return response_data["results"]
        return response_data

    def _windows_url(self) -> str:
        return f"{self.base_url}/sites/{self.site_id}/windows?attributes=1"

    def _groups_url(self) -> str:
        return f"{self.base_url}/sites/{self.site_id}/groups"

    def _group_detail_url(self, group_id: str) -> str:
        return f"{self.base_url}/sites/{self.site_id}/groups/{group_id}"

    def _get_group_details(self, group_id: str) -> Optional[Dict[str, Any]]:
        try:
            response = requests.get(
                self._group_detail_url(group_id), headers=self.headers, timeout=10
            )
            if response.status_code != 200:
                logger.error(
                    f"Failed to get group details for {group_id}: {response.status_code}"
                )
                return None
            details = self._extract_results(response.json())
            if not isinstance(details, dict):
                logger.error(f"Unexpected group details format for {group_id}: {type(details)}")
                return None
            return details
        except Exception as e:
            logger.error(f"Error retrieving group details for {group_id}: {e}")
            return None

    def _list_windows(self) -> List[Dict[str, Any]]:
        response = requests.get(self._windows_url(), headers=self.headers, timeout=10)
        if response.status_code != 200:
            logger.error(f"Failed to list windows: {response.status_code}")
            return []

        windows = self._extract_results(response.json())
        if not isinstance(windows, list):
            logger.error(f"Unexpected windows response format: {type(windows)}")
            return []

        valid_windows: List[Dict[str, Any]] = []
        for window in windows:
            if not isinstance(window, dict):
                logger.warning(f"Skipping invalid window entry: {window}")
                continue
            window_id = window.get("id")
            if not isinstance(window_id, str) or not window_id:
                logger.warning(f"Window entry missing id: {window}")
                continue
            self.window_cache[window_id] = window
            valid_windows.append(window)
        return valid_windows

    def _resolve_single_window_group(self, window_id: str) -> Optional[Group]:
        for group in self.list_groups():
            if len(group.member_ids) == 1 and group.member_ids[0] == window_id:
                return group
        return None

    def _member_ids_for_group(self, group_id: str) -> List[str]:
        group = next((group for group in self.list_groups() if group.id == group_id), None)
        return list(group.member_ids) if group else []

    def _create_group_request(self, name: str, window_ids: List[str]) -> Optional[Dict[str, Any]]:
        payload = {
            "group": {
                "name": name,
                "windows": window_ids,
            }
        }
        response = requests.post(
            self._groups_url(),
            headers=self.headers,
            json=payload,
            timeout=10,
        )
        logger.info(
            f"Halio create group response: status={response.status_code} "
            f"body={response.text[:500]}"
        )
        if response.status_code not in (200, 201):
            logger.error(f"Failed to create group {name}: {response.status_code}")
            return None
        results = self._extract_results(response.json())
        if not isinstance(results, dict):
            logger.error(f"Unexpected create-group response format for {name}: {type(results)}")
            return None
        return results

    def _ensure_single_window_groups(self, windows: List[Dict[str, Any]]) -> None:
        if self._ensured_single_window_groups:
            return

        groups = self.list_groups()
        existing_singletons = {
            tuple(group.member_ids): group
            for group in groups
            if len(group.member_ids) == 1
        }

        created_any = False
        for window in windows:
            window_id = window.get("id")
            if not isinstance(window_id, str):
                continue
            if (window_id,) in existing_singletons:
                continue
            group_name = window.get("name", f"Window {window_id}")
            logger.info(
                f"Creating missing single-window Halio group for {group_name} ({window_id})"
            )
            created = self._create_group_request(group_name, [window_id])
            if created:
                created_any = True

        self._ensured_single_window_groups = True
        if created_any:
            logger.info("Created one or more missing single-window Halio groups")

    def _get_window_state(self, window_id: str) -> Optional[Dict]:
        """Query current state of a window from Halio API."""
        try:
            url = f"{self.base_url}/sites/{self.site_id}/windows/{window_id}/live-tint-data"
            response = requests.get(url, headers=self.headers, timeout=10)

            if response.status_code == 200:
                data = response.json()
                # Handle wrapped response structure
                # API returns: {"statusCode": 200, "success": true, "results": {"level": 0, ...}}
                if isinstance(data, dict) and "results" in data:
                    results = data["results"]
                    if isinstance(results, dict):
                        # Extract level from results object
                        current_tint = results.get("level", 0)
                    else:
                        current_tint = 0
                else:
                    # No results field (shouldn't happen for 200, but handle gracefully)
                    current_tint = 0
                
                # Only update cache if we don't have it, or if the tint level changed
                # Don't update last_updated timestamp - that should only change when WE send a command
                if window_id not in self._state_cache:
                    self._state_cache[window_id] = {
                        "current_tint": current_tint,
                        "last_updated": 0,  # Initialize to 0 so first change is always allowed
                    }
                elif self._state_cache[window_id].get("current_tint") != current_tint:
                    # Tint level changed externally - reset timestamp to allow changes
                    self._state_cache[window_id]["current_tint"] = current_tint
                    self._state_cache[window_id]["last_updated"] = 0
                else:
                    # Just update the current tint, keep the last_updated timestamp
                    self._state_cache[window_id]["current_tint"] = current_tint
                
                return self._state_cache[window_id]
            elif response.status_code == 206:
                # No Tint Data - API returns: {"statusCode": 200, "message": "No Tint Data", "success": true}
                logger.debug(f"No tint data available for window {window_id}")
                # Return None to indicate no data available
                return None
            elif response.status_code == 404:
                logger.error(f"Window {window_id} not found")
                return None
            else:
                logger.error(f"Failed to get window state: {response.status_code} - {response.text}")
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
            windows = self._list_windows()
            self._ensure_single_window_groups(windows)
            panels = []

            for window in windows:
                window_id = window.get("id")
                panel_name = window.get("name", f"Window {window_id}")

                # Get live tint data for each window
                state = self._get_window_state(window_id)
                current_tint = state.get("current_tint", 0) if state else 0

                panel = Panel(
                    id=window_id,
                    name=panel_name,
                    level=current_tint,
                    last_change_ts=state.get("last_updated", 0) if state else 0,
                )
                panels.append(panel)

            return sorted(panels, key=lambda panel: panel.name.lower())

        except Exception as e:
            logger.error(f"Error listing panels: {e}")
            return []

    def list_groups(self) -> List[Group]:
        """
        Fetch all groups from Halio API and convert to Group objects.
        """
        try:
            response = requests.get(self._groups_url(), headers=self.headers, timeout=10)

            if response.status_code != 200:
                logger.error(f"Failed to list groups: {response.status_code}")
                return []

            halio_groups = self._extract_results(response.json())
            if not isinstance(halio_groups, list):
                logger.error(f"Unexpected groups response format: {type(halio_groups)}")
                return []

            groups = []

            for hg in halio_groups:
                if not isinstance(hg, dict):
                    logger.warning(f"Skipping invalid group entry: {hg}")
                    continue
                    
                group_id = hg.get("id")
                if not group_id:
                    logger.warning(f"Group entry missing id: {hg}")
                    continue

                details = self._get_group_details(group_id)
                windows = details.get("windows", []) if details else []
                member_ids = [
                    window.get("id")
                    for window in windows
                    if isinstance(window, dict) and isinstance(window.get("id"), str)
                ]

                group = Group(id=group_id, name=hg.get("name", f"Group {group_id}"), member_ids=member_ids)
                groups.append(group)

            return sorted(groups, key=lambda group: group.name.lower())

        except Exception as e:
            logger.error(f"Error listing groups: {e}")
            return []

    def set_panel(self, panel_id: str, level: TintLevel, min_dwell: int) -> bool:
        """
        Set tint level for a single panel via Halio API.

        Returns True if command accepted, False if dwell time not met or error.
        """
        window_id = panel_id
        if window_id not in self.window_cache:
            self._list_windows()
        window = self.window_cache.get(window_id)
        if not window:
            logger.error(f"Window {window_id} was not found on Halio")
            raise KeyError(f"Window {window_id} not found on Halio")

        # Check dwell time
        if not self._can_change(window_id, min_dwell):
            logger.info(f"Dwell time not met for panel {panel_id}")
            return False

        single_window_group = self._resolve_single_window_group(window_id)
        if not single_window_group:
            self._create_group_request(window.get("name", f"Window {window_id}"), [window_id])
            single_window_group = self._resolve_single_window_group(window_id)
        if single_window_group:
            logger.info(
                f"Using Halio single-window group {single_window_group.id} for window {window_id} "
                f"instead of direct window tint"
            )
            applied = self._send_group_tint(
                single_window_group.id,
                level,
                expected_panel_ids=[window_id],
            )
            return applied is not None

        logger.error(
            f"No single-window Halio group exists for window {window.get('name', window_id)} ({window_id}). "
            "Create one in Halio before using individual control."
        )
        raise KeyError(f"No single-window group exists for window {window_id}")

    def _send_group_tint(
        self,
        group_id: str,
        level: TintLevel,
        expected_panel_ids: Optional[List[str]] = None,
    ) -> Optional[List[str]]:
        """Send a Halio group tint command and return affected panel IDs when known."""
        try:
            url = f"{self.base_url}/sites/{self.site_id}/groups/{group_id}/tint"
            payload = {"level": int(level)}

            logger.info(
                f"Sending tint command to Halio for group: group={group_id} "
                f"level={level} payload={payload} url={url}"
            )

            response = requests.post(
                url, headers=self.headers, json=payload, timeout=10
            )

            logger.info(
                f"Halio API response for group {group_id}: "
                f"status={response.status_code} "
                f"body={response.text[:500]}"
            )

            if response.status_code == 202:
                logger.info(
                    f"✓ Tint command ACCEPTED for group {group_id} → level {level}"
                )
                try:
                    response_data = response.json()
                    queue_id = response_data.get("queueId", "N/A")
                    logger.info(f"  Queue ID: {queue_id}")
                except Exception:
                    pass

                applied = expected_panel_ids or self._member_ids_for_group(group_id)
                for window_id in applied:
                    self._state_cache[window_id] = {
                        "current_tint": int(level),
                        "last_updated": time.time(),
                    }

                if applied:
                    logger.info(f"  Applied to {len(applied)} panels: {applied}")
                else:
                    logger.info(
                        f"  Group {group_id} accepted; member panel IDs are unknown in this deployment"
                    )
                return applied
            if response.status_code == 404:
                logger.error(f"✗ Group {group_id} not found on Halio API")
                raise KeyError(f"Group {group_id} not found on Halio")

            logger.error(
                f"✗ Halio API error for group {group_id}: "
                f"status={response.status_code} body={response.text}"
            )
            return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error setting group {group_id}: {e}")
            return None
        except KeyError:
            raise
        except Exception as e:
            logger.error(f"Error setting group {group_id}: {e}")
            return None

    def set_group(self, group_id: str, level: TintLevel, min_dwell: int) -> Optional[List[str]]:
        """
        Set tint level for a group via Halio API.

        Returns list of panel IDs that were successfully updated when known.
        Returns [] when Halio accepted the group command but the member panel IDs
        are not known. Returns None on failure.
        """
        return self._send_group_tint(group_id, level)

    def create_group(self, name: str, member_ids: List[str], layout: GroupLayout | None = None) -> Group:
        created = self._create_group_request(name, member_ids)
        if not created:
            raise RuntimeError("failed to create Halio group")

        group_id = created.get("id")
        if not isinstance(group_id, str) or not group_id:
            raise RuntimeError("Halio group creation did not return a valid group id")

        details = self._get_group_details(group_id)
        windows = details.get("windows", []) if details else []
        member_ids = [
            window.get("id")
            for window in windows
            if isinstance(window, dict) and isinstance(window.get("id"), str)
        ]
        return Group(
            id=group_id,
            name=created.get("name", name),
            member_ids=member_ids,
            layout=normalize_group_layout(member_ids, layout),
        )
