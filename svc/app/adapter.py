from __future__ import annotations
import json
import os
import time
import threading
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
            "X-API-Key": HALIO_API_KEY,
            "Content-Type": "application/json"
        }

        # Load panel ID to Halio window UUID mapping
        self.panel_to_window: Dict[str, str] = self._load_window_mapping()
        self.window_to_panel: Dict[str, str] = {
            v: k for k, v in self.panel_to_window.items()
        }

        # Cache for window states to enforce dwell time
        self._state_cache: Dict[str, Dict] = {}

        # Mapping from panel_id to group_id (for workaround: one group per panel)
        self.panel_to_group: Dict[str, str] = {}

        logger.info(f"RealAdapter initialized for site {self.site_id}")
        logger.info(f"Loaded {len(self.panel_to_window)} panel mappings")
        
        # Initialize groups: ensure each panel has a corresponding group
        self._ensure_panel_groups()

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

    def _ensure_panel_groups(self) -> None:
        """
        Initialize groups: ensure each panel has a corresponding group.
        This is a workaround for API issues with individual window tinting.
        Groups are named the same as their panel IDs (e.g., "P01", "SK1").
        """
        try:
            # Get all existing groups
            existing_groups = self.list_groups()
            existing_group_names = {g.name for g in existing_groups}
            
            # Build panel_id -> group_id mapping from existing groups
            for group in existing_groups:
                # If group name matches a panel ID, map it
                if group.name in self.panel_to_window:
                    self.panel_to_group[group.name] = group.id
            
            # Find panels that don't have groups yet
            missing_panels = []
            for panel_id in self.panel_to_window.keys():
                if panel_id not in self.panel_to_group:
                    missing_panels.append(panel_id)
            
            if missing_panels:
                logger.info(
                    f"Found {len(missing_panels)} panels without groups. "
                    f"Creating groups: {missing_panels}"
                )
                
                # Create groups for missing panels
                for panel_id in missing_panels:
                    try:
                        # Create a group with the panel ID as the name and member
                        group = self.create_group(panel_id, [panel_id])
                        self.panel_to_group[panel_id] = group.id
                        logger.info(f"Created group '{panel_id}' (ID: {group.id}) for panel {panel_id}")
                    except Exception as e:
                        logger.error(f"Failed to create group for panel {panel_id}: {e}")
            else:
                logger.info("All panels have corresponding groups")
                
        except Exception as e:
            logger.error(f"Error ensuring panel groups: {e}")

    def create_group(self, name: str, member_ids: List[str]) -> Group:
        """
        Create a new group via Halio API.
        
        Args:
            name: Group name (should match panel ID for workaround)
            member_ids: List of panel IDs to include in the group
            
        Returns:
            Created Group object
        """
        try:
            # Convert panel IDs to window UUIDs
            window_uuids = []
            for panel_id in member_ids:
                window_uuid = self.panel_to_window.get(panel_id)
                if window_uuid:
                    window_uuids.append(window_uuid)
                else:
                    logger.warning(f"Panel {panel_id} not found in window mapping, skipping")
            
            if not window_uuids:
                raise ValueError(f"No valid windows found for panels: {member_ids}")
            
            url = f"{self.base_url}/sites/{self.site_id}/groups"
            # Halio API expects: {"group": {"name": "string", "windows": ["string"]}}
            payload = {
                "group": {
                    "name": name,
                    "windows": window_uuids
                }
            }
            
            logger.info(
                f"Creating group via Halio API: name={name} "
                f"panels={member_ids} windows={window_uuids} url={url}"
            )
            
            response = requests.post(
                url, headers=self.headers, json=payload, timeout=10
            )
            
            logger.info(
                f"Halio API response for create group '{name}': "
                f"status={response.status_code} body={response.text[:500]}"
            )
            
            if response.status_code == 201:
                response_data = response.json()
                # Extract group data from response
                # API may return wrapped response: {"statusCode": 201, "results": {...}}
                if isinstance(response_data, dict):
                    if "results" in response_data:
                        group_data = response_data["results"]
                    else:
                        group_data = response_data
                    
                    group_id = group_data.get("id")
                    if not group_id:
                        raise ValueError(f"Group created but no ID in response: {response_data}")
                    
                    group = Group(
                        id=group_id,
                        name=name,
                        member_ids=member_ids  # Use original panel IDs
                    )
                    logger.info(f"✓ Group '{name}' created successfully (ID: {group_id})")
                    return group
                else:
                    raise ValueError(f"Unexpected response format: {type(response_data)}")
            elif response.status_code == 400:
                error_msg = response.text
                logger.error(f"✗ Invalid group creation request: {error_msg}")
                raise ValueError(f"Invalid request: {error_msg}")
            else:
                error_msg = response.text
                logger.error(f"✗ Halio API error creating group: status={response.status_code} body={error_msg}")
                raise RuntimeError(f"API error: {error_msg}")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error creating group '{name}': {e}")
            raise
        except Exception as e:
            logger.error(f"Error creating group '{name}': {e}")
            raise

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
            url = f"{self.base_url}/sites/{self.site_id}/windows"
            response = requests.get(url, headers=self.headers, timeout=10)

            if response.status_code != 200:
                logger.error(f"Failed to list windows: {response.status_code}")
                return []

            response_data = response.json()
            # Extract results array from wrapped response
            if isinstance(response_data, dict) and "results" in response_data:
                windows = response_data["results"]
            elif isinstance(response_data, list):
                windows = response_data
            else:
                logger.error(f"Unexpected response format: {type(response_data)}")
                return []

            panels = []

            for window in windows:
                if not isinstance(window, dict):
                    logger.warning(f"Skipping invalid window entry: {window}")
                    continue
                    
                window_id = window.get("id")
                if not window_id:
                    logger.warning(f"Window entry missing id: {window}")
                    continue
                    
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
        Populates member_ids by matching group names to panel IDs.
        """
        try:
            url = f"{self.base_url}/sites/{self.site_id}/groups"
            response = requests.get(url, headers=self.headers, timeout=10)

            if response.status_code != 200:
                logger.error(f"Failed to list groups: {response.status_code}")
                return []

            response_data = response.json()
            # Extract results array from wrapped response
            if isinstance(response_data, dict) and "results" in response_data:
                halio_groups = response_data["results"]
            elif isinstance(response_data, list):
                halio_groups = response_data
            else:
                logger.error(f"Unexpected response format: {type(response_data)}")
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

                group_name = hg.get("name", f"Group {group_id}")
                
                # Determine member_ids based on group name
                # For workaround: groups are named after panel IDs (e.g., "P01", "SK1")
                member_ids = []
                if group_name in self.panel_to_window:
                    # This is a single-panel group (workaround)
                    member_ids = [group_name]
                    # Update panel_to_group mapping
                    self.panel_to_group[group_name] = group_id
                else:
                    # Try to get windows from group data if available
                    # Some APIs might return windows array
                    windows = hg.get("windows", [])
                    if isinstance(windows, list):
                        for window_uuid in windows:
                            panel_id = self.window_to_panel.get(window_uuid)
                            if panel_id:
                                member_ids.append(panel_id)

                group = Group(
                    id=group_id,
                    name=group_name,
                    member_ids=member_ids,
                )
                groups.append(group)

            return groups

        except Exception as e:
            logger.error(f"Error listing groups: {e}")
            return []

    def set_panel(self, panel_id: str, level: TintLevel, min_dwell: int) -> bool:
        """
        Set tint level for a single panel via Halio API.
        Uses group tinting as a workaround for individual window tinting issues.

        Returns True if command accepted, False if dwell time not met or error.
        """
        # Translate panel ID to window UUID (for dwell time checking)
        window_id = self.panel_to_window.get(panel_id)
        if not window_id:
            logger.error(f"Panel {panel_id} not found in window mapping")
            raise KeyError(f"Panel {panel_id} not mapped to Halio window UUID")

        # Get the group ID for this panel (workaround: one group per panel)
        group_id = self.panel_to_group.get(panel_id)
        if not group_id:
            logger.error(
                f"Panel {panel_id} does not have a corresponding group. "
                "This should have been created during initialization."
            )
            raise KeyError(f"Panel {panel_id} not mapped to a group")

        # Check dwell time (using window_id for consistency)
        if not self._can_change(window_id, min_dwell):
            logger.info(f"Dwell time not met for panel {panel_id}")
            return False

        try:
            # WORKAROUND: Use group tinting instead of individual window tinting
            # POST to Halio API group tint endpoint
            url = f"{self.base_url}/sites/{self.site_id}/groups/{group_id}/tint"
            payload = {"level": int(level)}  # Halio API expects "level", not "tintLevel"
            
            logger.info(
                f"Sending tint command via GROUP (workaround): panel={panel_id} "
                f"group={group_id} window={window_id} level={level} "
                f"payload={payload} url={url}"
            )

            response = requests.post(
                url, headers=self.headers, json=payload, timeout=10
            )
            
            # Log full response details at INFO level
            logger.info(
                f"Halio API response for panel {panel_id} (via group {group_id}): "
                f"status={response.status_code} "
                f"headers={dict(response.headers)} "
                f"body={response.text[:500]}"  # Limit body to 500 chars
            )

            # Halio returns 202 Accepted for async commands
            if response.status_code == 202:
                logger.info(
                    f"✓✓✓ Tint command ACCEPTED for panel {panel_id} → level {level} "
                    f"(via group {group_id}, window {window_id}) ✓✓✓"
                )
                # Parse response to get queue ID if available
                try:
                    response_data = response.json()
                    queue_id = response_data.get("queueId", "N/A")
                    message = response_data.get("message", "N/A")
                    logger.info(f"  Queue ID: {queue_id}")
                    logger.info(f"  Message: {message}")
                except Exception:
                    pass
                # Update cache
                self._state_cache[window_id] = {
                    "current_tint": int(level),
                    "last_updated": time.time(),
                }
                
                # Verify the command actually executed after a delay
                # Halio commands are async, so check after a few seconds
                def verify_tint_change():
                    time.sleep(5)  # Wait 5 seconds for command to execute
                    logger.info(f"Verifying tint change for panel {panel_id} (window {window_id})...")
                    state = self._get_window_state(window_id)
                    if state:
                        actual_level = state.get("current_tint", "unknown")
                        expected_level = int(level)
                        if actual_level == expected_level:
                            logger.info(f"VERIFIED: Panel {panel_id} is now at level {actual_level} (as expected)")
                        else:
                            logger.warning(
                                f"X - MISMATCH: Panel {panel_id} expected level {expected_level} "
                                f"but actual level is {actual_level}"
                            )
                    else:
                        logger.warning(f"! - Could not verify tint change for panel {panel_id}")
                
                # Start verification in background thread
                verify_thread = threading.Thread(target=verify_tint_change, daemon=True)
                verify_thread.start()
                
                return True
            elif response.status_code == 404:
                logger.error(f"✗ Group {group_id} not found on Halio API")
                raise KeyError(f"Group {group_id} not found on Halio")
            elif response.status_code == 400:
                logger.error(
                    f"✗ Invalid tint command for panel {panel_id}: "
                    f"status={response.status_code} body={response.text}"
                )
                return False
            else:
                logger.error(
                    f"✗ Halio API error for panel {panel_id}: "
                    f"status={response.status_code} body={response.text}"
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
            payload = {"level": int(level)}  # Halio API expects "level", not "tintLevel"
            
            logger.info(
                f"Sending tint command to Halio for group: group={group_id} "
                f"level={level} payload={payload} url={url}"
            )

            response = requests.post(
                url, headers=self.headers, json=payload, timeout=10
            )
            
            # Log full response details at INFO level
            logger.info(
                f"Halio API response for group {group_id}: "
                f"status={response.status_code} "
                f"body={response.text[:500]}"  # Limit body to 500 chars
            )

            if response.status_code == 202:
                logger.info(
                    f"✓ Tint command ACCEPTED for group {group_id} → level {level}"
                )
                # Parse response to get queue ID if available
                try:
                    response_data = response.json()
                    queue_id = response_data.get("queueId", "N/A")
                    logger.info(f"  Queue ID: {queue_id}")
                except Exception:
                    pass
                # Get group members
                groups = self.list_groups()
                for g in groups:
                    if g.id == group_id:
                        # Update cache for all members
                        for panel_id in g.member_ids:
                            window_id = self.panel_to_window.get(panel_id)
                            if window_id:
                                self._state_cache[window_id] = {
                                    "current_tint": int(level),
                                    "last_updated": time.time(),
                                }
                        logger.info(f"  Applied to {len(g.member_ids)} panels: {g.member_ids}")
                        return g.member_ids
                logger.warning(f"Group {group_id} accepted but members not found")
                return []
            elif response.status_code == 404:
                logger.error(f"✗ Group {group_id} not found on Halio API")
                raise KeyError(f"Group {group_id} not found on Halio")
            else:
                logger.error(
                    f"✗ Halio API error for group {group_id}: "
                    f"status={response.status_code} body={response.text}"
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
