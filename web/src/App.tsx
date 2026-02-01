import React, { useEffect, useState } from "react";
import { api} from "./api";
import {Panel, Group} from "./types"

import PanelGrid from "./components/PanelGrid";

export default function App() {
    const [health, setHealth] = useState<string>("checking");
    const [panels, setPanels] = useState<Panel[]>([]);
    const [groups, setGroups] = useState<Group[]>([]);
    const [busy, setBusy] = useState<string | null>(null);
    const [groupLevel, setGroupLevel] = useState<number>(50);
    const [groupId, setGroupId] = useState<string>("");

    async function refresh() {
        const [p, g, h] = await Promise.all([api.panels(), api.groups(), api.health()]);
        setPanels(p);
        setGroups(g);
        setHealth(`${h.status}  mode  ${h.mode}`);
        if (!groupId && g.length) setGroupId(g[0].id);
    }

    useEffect(() => {
        refresh().catch(err => setHealth(`error  ${String(err)}`));
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    async function setPanel(panelId: string, level: number) {
        try {
            setBusy(panelId);
            await api.setPanelLevel(panelId, level);
            await refresh();
        } catch (e) {
            alert(String(e));
        } finally {
            setBusy(null);
        }
    }

    async function setGroup() {
        if (!groupId) return;
        try {
            setBusy(groupId);
            await api.setGroupLevel(groupId, groupLevel);
            await refresh();
        } catch (e) {
            alert(String(e));
        } finally {
            setBusy(null);
        }
    }

    return (
        <>
            <header className="header">
                <div className="header-inner">
                    <div className="brand">
                        <span className="dot" />
                        <span>Electrochromic Control</span>
                    </div>
                    <span className="pill">
                        <span>status</span>
                        <strong>{health}</strong>
                    </span>
                </div>
            </header>

            <div className="container">
                <div className="section">
                    <h2>Group control</h2>
                    <div className="toolbar">
                        <label htmlFor="group-select" className="pill">group</label>
                        <select
                            id="group-select"
                            value={groupId}
                            onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setGroupId(e.target.value)}
                        >
                            {groups.map(g => (
                                <option key={g.id} value={g.id}>{g.name}  {g.id}</option>
                            ))}
                        </select>

                        <input
                            type="number"
                            min={0}
                            max={100}
                            value={groupLevel}
                            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setGroupLevel(Number(e.target.value))}
                        />
                        <button onClick={setGroup} disabled={!groupId || busy === groupId}>
                            {busy === groupId ? "Setting..." : "Set group"}
                        </button>

                        <div className="chips">
                            {[0, 25, 50, 75, 100].map(v => (
                                <span key={v} className="chip" onClick={() => setGroupLevel(v)}>{v}</span>
                            ))}
                        </div>
                    </div>
                </div>

                <PanelGrid panels={panels} onSet={setPanel} busyId={busy} />
                <div className="footer-space" />
            </div>
        </>
    );
}
