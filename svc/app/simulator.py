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

        # enforce dwell before accepting
        if not self._can_change(p, min_dwell):
            return False

        # mark dwell immediately so back to back requests are throttled
        now = time.time()
        p.last_change_ts = now
        save_snapshot(self.snap)

        # perform the visible change asynchronously after a realistic delay
        def _commit(panel_id=panel_id):
            time.sleep(2.0)  # simulate transition time
            panel = self.snap.panels[panel_id]
            panel.level = int(level)
            panel.last_change_ts = time.time()
            save_snapshot(self.snap)

        t = threading.Thread(target=_commit, daemon=True)
        t.start()
        return True


    def set_group(self, group_id: str, level: TintLevel, min_dwell: int) -> List[str]:
        if group_id not in self.snap.groups:
            raise KeyError(group_id)

        applied: List[str] = []
        threads: List[threading.Thread] = []

        for pid in self.snap.groups[group_id].member_ids:
            if pid not in self.snap.panels:
                continue
            p = self.snap.panels[pid]
            if not self._can_change(p, min_dwell):
                continue

            # reserve dwell and schedule work
            p.last_change_ts = time.time()
            save_snapshot(self.snap)

            def _commit(panel_id=pid):
                time.sleep(2.0)
                panel = self.snap.panels[panel_id]
                panel.level = int(level)
                panel.last_change_ts = time.time()
                save_snapshot(self.snap)

            t = threading.Thread(target=_commit, daemon=True)
            t.start()
            threads.append(t)
            applied.append(pid)

        # do not join threads  let the API return quickly
        return applied

    def create_group(self, name: str, member_ids: List[str]) -> Group:
        # validate panel ids
        for pid in member_ids:
            if pid not in self.snap.panels:
                raise KeyError(f"panel id not found: {pid}")
        # generate unique group id G-1 G-2 ...
        n = 1
        gid = f"G-{n}"
        while gid in self.snap.groups:
            n += 1
            gid = f"G-{n}"
        g = Group(id=gid, name=name, member_ids=list(member_ids))
        self.snap.groups[gid] = g
        save_snapshot(self.snap)
        return g


    def create_group(self, name: str, member_ids: List[str]) -> Group:
        # generate a simple id like G-1 G-2 ...
        existing_ids = set(self.snap.groups.keys())
        n = 1
        while f"G-{n}" in existing_ids:
            n += 1
        gid = f"G-{n}"

        # filter to only valid panel ids
        valid_ids = [pid for pid in member_ids if pid in self.snap.panels]

        group = Group(id=gid, name=name, member_ids=valid_ids)
        self.snap.groups[gid] = group

        # update panels to point at this group if you care about Panel.group_id
        for pid in valid_ids:
            p = self.snap.panels[pid]
            p.group_id = gid

        save_snapshot(self.snap)
        return group

    def update_group(
        self,
        group_id: str,
        name: str | None,
        member_ids: List[str] | None,
    ) -> Group:
        if group_id not in self.snap.groups:
            raise KeyError(group_id)

        g = self.snap.groups[group_id]

        if name is not None:
            g.name = name

        if member_ids is not None:
            # normalize to only existing panels
            new_ids = [pid for pid in member_ids if pid in self.snap.panels]
            old_set = set(g.member_ids)
            new_set = set(new_ids)

            # clear group_id from panels leaving this group
            for pid in old_set - new_set:
                p = self.snap.panels.get(pid)
                if p and p.group_id == group_id:
                    p.group_id = None

            # assign group_id to new members
            for pid in new_set:
                p = self.snap.panels.get(pid)
                if p:
                    p.group_id = group_id

            g.member_ids = list(new_set)

        save_snapshot(self.snap)
        return g

    def delete_group(self, group_id: str) -> bool:
        if group_id not in self.snap.groups:
            return False

        # clear group_id from member panels
        member_ids = list(self.snap.groups[group_id].member_ids)
        for pid in member_ids:
            p = self.snap.panels.get(pid)
            if p and p.group_id == group_id:
                p.group_id = None

        del self.snap.groups[group_id]
        save_snapshot(self.snap)
        return True
