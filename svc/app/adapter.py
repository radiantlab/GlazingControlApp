from __future__ import annotations
import json
import os
import time
import threading
import logging
from typing import List, Dict, Optional, Tuple, Set
from .models import Panel, Group, TintLevel
from .state import load_groups
from .config import (
    HALIO_API_URL,
    HALIO_SITE_ID,
    HALIO_API_KEY,
    WINDOW_MAPPING_FILE,
    GROUP_MAPPING_FILE,
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

        # Load local group ID to Halio group UUID mapping
        self.group_to_halio: Dict[str, str] = self._load_group_mapping()
        self.halio_to_group: Dict[str, str] = {
            v: k for k, v in self.group_to_halio.items()
        }

        # Cache for window states to enforce dwell time
        self._state_cache: Dict[str, Dict] = {}

        logger.info(f"RealAdapter initialized for site {self.site_id}")
        logger.info(f"Loaded {len(self.panel_to_window)} panel mappings")
        logger.info(f"Loaded {len(self.group_to_halio)} group mappings")

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

    def _load_group_mapping(self) -> Dict[str, str]:
        """
        Load mapping from local group IDs (e.g., G-facade) to Halio group UUIDs.

        The mapping file should be JSON format:
        {
            "G-facade": "uuid-for-halion-group",
            "G-skylights": "uuid-for-halion-group",
            ...
        }
        """
        if not os.path.exists(GROUP_MAPPING_FILE):
            logger.warning(
                f"Group mapping file not found: {GROUP_MAPPING_FILE}. "
                "Creating empty mapping. You must populate this file with actual UUIDs."
            )
            return {}

        try:
            with open(GROUP_MAPPING_FILE, "r", encoding="utf-8") as f:
                mapping = json.load(f)
            # Filter out comment keys (starting with '_') and empty values
            cleaned: Dict[str, str] = {}
            for k, v in mapping.items():
                if k.startswith("_"):
                    continue
                if isinstance(v, str) and v.strip():
                    cleaned[k] = v.strip()
            return cleaned
        except Exception as e:
            logger.error(f"Failed to load group mapping: {e}")
            return {}

    def _resolve_group_ids(self, group_id: str) -> tuple[str, Optional[str]]:
        """
        Resolve a provided group ID to the Halio group UUID.

        Returns (halio_group_id, local_group_id_or_none).
        """
        if group_id in self.group_to_halio:
            return self.group_to_halio[group_id], group_id
        if group_id in self.halio_to_group:
            return group_id, self.halio_to_group[group_id]
        return group_id, None

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

            local_groups: Dict[str, Group] = {}
            try:
                local_groups = load_groups()
            except Exception as e:
                logger.warning(f"Failed to load local group mapping: {e}")

            # Index Halio groups by id for quick lookup
            halio_by_id: Dict[str, Dict] = {}
            for hg in halio_groups:
                if isinstance(hg, dict) and hg.get("id"):
                    halio_by_id[hg["id"]] = hg

            groups: List[Group] = []
            mapped_halio_ids: Set[str] = set()

            # Prefer local groups for membership (Halio group list doesn't include members)
            for local_id, local_group in local_groups.items():
                halio_id = self.group_to_halio.get(local_id)
                halio_group = halio_by_id.get(halio_id) if halio_id else None
                name = (
                    halio_group.get("name", local_group.name)
                    if halio_group
                    else local_group.name
                )

                groups.append(
                    Group(
                        id=local_id,
                        name=name,
                        member_ids=list(local_group.member_ids),
                        hidden=bool(getattr(local_group, "hidden", False)),
                    )
                )
                if halio_id:
                    mapped_halio_ids.add(halio_id)

            # Add any remaining Halio groups not mapped to local IDs
            for hg in halio_groups:
                if not isinstance(hg, dict):
                    logger.warning(f"Skipping invalid group entry: {hg}")
                    continue

                group_id = hg.get("id")
                if not group_id:
                    logger.warning(f"Group entry missing id: {hg}")
                    continue
                if group_id in mapped_halio_ids:
                    continue

                member_ids: List[str] = []
                raw_member_ids = None
                for key in ("member_ids", "memberIds", "members", "window_ids", "windowIds", "windows"):
                    if isinstance(hg.get(key), list):
                        raw_member_ids = hg.get(key)
                        break
                if raw_member_ids:
                    member_ids = [
                        self.window_to_panel.get(member_id, member_id)
                        for member_id in raw_member_ids
                        if isinstance(member_id, str)
                    ]

                groups.append(
                    Group(
                        id=group_id,
                        name=hg.get("name", f"Group {group_id}"),
                        member_ids=member_ids,
                        hidden=False,
                    )
                )

            return groups
        except Exception as e:
            logger.error(f"Error listing groups: {e}")
            return []

    def create_group(self, name: str, member_ids: List[str], hidden: bool = False) -> Group:
        """
        Create a new group via Halio API and update local mapping.
        """
        try:
            # POST to Halio API to create group
            url = f"{self.base_url}/sites/{self.site_id}/groups"
            
            # Map local panel IDs to Halio window UUIDs
            window_ids = []
            for pid in member_ids:
                if pid in self.panel_to_window:
                    window_ids.append(self.panel_to_window[pid])
                else:
                    logger.warning(f"Panel {pid} not mapped to a window UUID, skipping for group creation")
                    
            payload = {
                "group": {
                    "name": name,
                    "windows": window_ids
                }
            }
            
            logger.info(f"Creating group in Halio API: name={name} payload={payload} url={url}")

            response = requests.post(
                url, headers=self.headers, json=payload, timeout=10
            )

            if response.status_code in (201, 202):
                response_data = response.json()
                # Halio API typically returns the created group details in 'results' or the root JSON
                group_data = response_data.get("results", response_data)
                
                if isinstance(group_data, list) and len(group_data) > 0:
                    group_data = group_data[0]
                    
                halio_group_id = group_data.get("id")
                
                if not halio_group_id:
                    logger.error(f"Failed to extract group ID from Halio response: {response_data}")
                    raise RuntimeError("Failed to extract group ID from Halio response")
                
                # We need a local ID. The state.py creates things like "G-P01".
                # To be safe, let's use the provided name, slightly cleaned up, or a fallback.
                local_id = f"G-{name.replace('Panel ', '')}"
                if " " in local_id:
                     # fallback if it's not a panel name
                     import uuid
                     local_id = f"G-custom-{uuid.uuid4().hex[:6]}"

                logger.info(f"✓ Group created in Halio API: local_id={local_id} halio_id={halio_group_id}")
                
                # Update our in-memory mappings
                self.group_to_halio[local_id] = halio_group_id
                self.halio_to_group[halio_group_id] = local_id
                
                # Save the mapping to the file
                self._save_group_mapping()

                return Group(
                    id=local_id,
                    name=name,
                    member_ids=member_ids,
                    hidden=hidden,
                )
            else:
                 logger.error(f"✗ Failed to create group in Halio API: status={response.status_code} body={response.text}")
                 raise RuntimeError(f"Failed to create group in Halio API: {response.text}")

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error creating group {name}: {e}")
            raise RuntimeError(f"Network error creating group {name}: {e}")
        except Exception as e:
            logger.error(f"Error creating group {name}: {e}")
            raise RuntimeError(f"Error creating group {name}: {e}")

    def _save_group_mapping(self) -> None:
        """Save the current group mapping to the mapping file."""
        try:
            # We try to load existing to preserve any comments or unknown keys, 
            # but if it fails or doesn't exist, we start fresh.
            mapping = {}
            if os.path.exists(GROUP_MAPPING_FILE):
                try:
                    with open(GROUP_MAPPING_FILE, "r", encoding="utf-8") as f:
                         mapping = json.load(f)
                except Exception:
                     pass
                     
            # Update with our current mapping
            mapping.update(self.group_to_halio)
            
            with open(GROUP_MAPPING_FILE, "w", encoding="utf-8") as f:
                 json.dump(mapping, f, indent=4)
                 
            logger.info(f"Saved {len(self.group_to_halio)} group mappings to {GROUP_MAPPING_FILE}")
        except Exception as e:
             logger.error(f"Failed to save group mapping: {e}")

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
            payload = {"level": int(level)}  # Halio API expects "level", not "tintLevel"
            
            logger.info(
                f"Sending tint command to Halio: panel={panel_id} window={window_id} "
                f"level={level} payload={payload} url={url}"
            )

            response = requests.post(
                url, headers=self.headers, json=payload, timeout=10
            )
            
            # Log full response details at INFO level
            logger.info(
                f"Halio API response for panel {panel_id}: "
                f"status={response.status_code} "
                f"headers={dict(response.headers)} "
                f"body={response.text[:500]}"  # Limit body to 500 chars
            )

            # Halio returns 202 Accepted for async commands
            if response.status_code == 202:
                logger.info(
                    f"✓✓✓ Tint command ACCEPTED for panel {panel_id} → level {level} "
                    f"(window {window_id}) ✓✓✓"
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
                logger.error(f"✗ Window {window_id} not found on Halio API")
                raise KeyError(f"Window {window_id} not found on Halio")
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

    def set_group(
        self, group_id: str, level: TintLevel, min_dwell: int
    ) -> Tuple[bool, List[str], str]:
        """
        Set tint level for a group via Halio API.

        Returns (ok, list of panel IDs updated, message).
        """
        try:
            halio_group_id, local_group_id = self._resolve_group_ids(group_id)
            # Halio supports group tinting directly
            url = f"{self.base_url}/sites/{self.site_id}/groups/{halio_group_id}/tint"
            payload = {"level": int(level)}  # Halio API expects "level", not "tintLevel"
            
            logger.info(
                f"Sending tint command to Halio for group: group={group_id} "
                f"halio_group={halio_group_id} level={level} payload={payload} url={url}"
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
                # Get group members (prefer local groups for membership)
                member_ids: List[str] = []
                if local_group_id:
                    try:
                        local_groups = load_groups()
                        local_group = local_groups.get(local_group_id)
                        if local_group:
                            member_ids = list(local_group.member_ids)
                    except Exception as e:
                        logger.warning(f"Failed to load local group members: {e}")

                # Fallback: try to find members from list_groups if we have no local mapping
                if not member_ids:
                    groups = self.list_groups()
                    for g in groups:
                        if g.id == group_id:
                            member_ids = list(g.member_ids)
                            break

                if member_ids:
                    # Update cache for all members
                    for panel_id in member_ids:
                        window_id = self.panel_to_window.get(panel_id)
                        if window_id:
                            self._state_cache[window_id] = {
                                "current_tint": int(level),
                                "last_updated": time.time(),
                            }
                    logger.info(f"  Applied to {len(member_ids)} panels: {member_ids}")
                    return True, member_ids, "group updated"

                logger.info(f"  Applied to 0 panels (members unknown)")
                return True, [], "group command accepted"
            elif response.status_code == 404:
                logger.error(f"✗ Group {halio_group_id} not found on Halio API")
                raise KeyError(f"Group {halio_group_id} not found on Halio")
            else:
                logger.error(
                    f"✗ Halio API error for group {group_id}: "
                    f"status={response.status_code} body={response.text}"
                )
                return False, [], "halio api error"

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error setting group {group_id}: {e}")
            return False, [], "network error"
        except KeyError:
            raise
        except Exception as e:
            logger.error(f"Error setting group {group_id}: {e}")
            return False, [], "unexpected error"
