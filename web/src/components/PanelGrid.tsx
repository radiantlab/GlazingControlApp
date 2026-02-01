import React from "react";
import type { Panel } from "../types";

type Props = {
    panels: Panel[];
    onSet: (panelId: string, level: number) => Promise<void>;
    busyId?: string | null;
};

export default function PanelGrid({ panels, onSet, busyId }: Props) {
    return (
        <div className="grid">
            {panels.map(p => {
                const knobLeft = `${p.level}%`;
                return (
                    <div key={p.id} className="card">
                        <div className="card-head">
                            <div className="card-title">{p.name}</div>
                            <span className="badge">ID {p.id}</span>
                        </div>

                        <div>
                            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, color: "var(--muted)" }}>
                                <span>tint</span>
                                <strong style={{ color: "var(--text)" }}>{p.level}</strong>
                            </div>
                            <div className="tbar">
                                <span className="tbar-dot" style={{ left: knobLeft }} />
                            </div>

                            <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}>
                                <input
                                    type="range"
                                    min={0}
                                    max={100}
                                    defaultValue={p.level}
                                    id={`range-${p.id}`}
                                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                                        const dot = (e.currentTarget.parentElement as HTMLElement).querySelector(".tbar-dot") as HTMLElement | null;
                                        if (dot) dot.style.left = `${e.currentTarget.value}%`;
                                    }}
                                />
                                <button
                                    onClick={async () => {
                                        const el = document.getElementById(`range-${p.id}`) as HTMLInputElement | null;
                                        const v = el ? Number(el.value) : p.level;
                                        const clamped = Math.max(0, Math.min(100, Number.isNaN(v) ? p.level : v));
                                        await onSet(p.id, clamped);
                                    }}
                                    disabled={busyId === p.id}
                                >
                                    {busyId === p.id ? "Setting..." : "Apply"}
                                </button>
                            </div>

                            <div className="chips">
                                {[0, 25, 50, 75, 100].map(v => (
                                    <span
                                        key={v}
                                        className="chip"
                                        onClick={() => {
                                            const el = document.getElementById(`range-${p.id}`) as HTMLInputElement | null;
                                            if (el) {
                                                el.value = String(v);
                                                const dot = (el.parentElement as HTMLElement).querySelector(".tbar-dot") as HTMLElement | null;
                                                if (dot) dot.style.left = `${v}%`;
                                            }
                                        }}
                                    >
                                        {v}
                                    </span>
                                ))}
                            </div>

                            <div style={{ marginTop: 8 }}>
                                <small className="mono">last ts  {Math.round(p.last_change_ts)}</small>
                            </div>
                        </div>
                    </div>
                );
            })}
        </div>
    );
}
