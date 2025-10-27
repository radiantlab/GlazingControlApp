export type Panel = {
    id: string;
    name: string;
    group_id?: string | null;
    level: number;
    last_change_ts: number;
};

export type Group = {
    id: string;
    name: string;
    member_ids: string[];
};

const API_BASE = (import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000").replace(/\/$/, "");

async function http<T>(path: string, options?: RequestInit): Promise<T> {
    const res = await fetch(`${API_BASE}${path}`, {
        headers: { "Content-Type": "application/json", ...(options?.headers || {}) },
        ...options
    });
    if (!res.ok) {
        const text = await res.text();
        throw new Error(`${res.status} ${text}`);
    }
    // some endpoints return no body (eg 204) so guard
    const contentType = res.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
        // @ts-ignore
        return (await res.text()) as T;
    }
    return (await res.json()) as T;
}

export const api = {
    health: () => http<{ status: string; mode: string }>("/health"),
    panels: () => http<Panel[]>("/panels"),
    groups: () => http<Group[]>("/groups"),
    setPanelLevel: (panelId: string, level: number) =>
        http<{ ok: boolean; applied_to: string[]; message: string }>("/commands/set-level", {
            method: "POST",
            body: JSON.stringify({ target_type: "panel", target_id: panelId, level })
        }),
    setGroupLevel: (groupId: string, level: number) =>
        http<{ ok: boolean; applied_to: string[]; message: string }>("/commands/set-level", {
            method: "POST",
            body: JSON.stringify({ target_type: "group", target_id: groupId, level })
        })
};
