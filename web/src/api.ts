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

export type AuditLogEntry = {
    ts: number
    actor: string
    target_type: "panel" | "group"
    target_id: string
    level: number
    applied_to: string[]
    result: string
};


const API_BASE = (import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000").replace(/\/$/, "");

async function http<T>(path: string, options?: RequestInit): Promise<T> {
    const res = await fetch(`${API_BASE}${path}`, {
        headers: { "Content-Type": "application/json", ...(options?.headers || {}) },
        ...options
    });
    if (!res.ok) {
        const text = await res.text();
        // Preserve status code in error message for dwell time detection
        const error = new Error(`${res.status} ${text}`);
        (error as any).status = res.status;
        throw error;
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
    createGroup: (name: string, memberIds: string[]) =>
        http<Group>("/groups", {
            method: "POST",
            body: JSON.stringify({ name, member_ids: memberIds })
        }),

    updateGroup: (groupId: string, name: string, memberIds: string[]) =>
        http<Group>(`/groups/${groupId}`, {
            method: "PATCH",
            body: JSON.stringify({ name, member_ids: memberIds })
        }),

    deleteGroup: (groupId: string) =>
        http<unknown>(`/groups/${groupId}`, {
            method: "DELETE"
        }),

    setPanelLevel: (panelId: string, level: number) =>
        http<{ ok: boolean; applied_to: string[]; message: string }>("/commands/set-level", {
            method: "POST",
            body: JSON.stringify({ target_type: "panel", target_id: panelId, level })
        }),

    setGroupLevel: (groupId: string, level: number) =>
        http<{ ok: boolean; applied_to: string[]; message: string }>("/commands/set-level", {
            method: "POST",
            body: JSON.stringify({ target_type: "group", target_id: groupId, level })
        }),

    auditLogs: (limit = 500) =>
        http<AuditLogEntry[]>(`/logs/audit?limit=${encodeURIComponent(limit)}`),

    exportAuditLogs: async (
        limit = 10000,
        startDate?: string,
        endDate?: string,
        targetType?: string,
        targetFilter?: string,
        resultFilter?: string
    ) => {
        const params = new URLSearchParams();
        params.append("limit", limit.toString());
        if (startDate) {
            // Parse date string as local date (start of day in user's timezone), then convert to UTC
            // This matches LogsPanel filtering logic to ensure export matches what users see in UI
            const [year, month, day] = startDate.split('-').map(Number);
            const date = new Date(year, month - 1, day, 0, 0, 0, 0);
            params.append("start_date", Math.floor(date.getTime() / 1000).toString());
        }
        if (endDate) {
            // Parse date string as local date (end of day in user's timezone), then convert to UTC
            // This matches LogsPanel filtering logic to ensure export matches what users see in UI
            const [year, month, day] = endDate.split('-').map(Number);
            const date = new Date(year, month - 1, day, 23, 59, 59, 999);
            const seconds = date.getTime() / 1000;
            // Include fractional seconds to match component's end-of-day handling
            params.append("end_date", seconds.toString());
        }
        if (targetType && targetType !== "all") {
            params.append("target_type", targetType);
        }
        if (targetFilter) {
            params.append("target_filter", targetFilter);
        }
        if (resultFilter) {
            params.append("result_filter", resultFilter);
        }
        
        const res = await fetch(`${API_BASE}/logs/audit/export?${params.toString()}`, {
            headers: { "Content-Type": "application/json" }
        });
        if (!res.ok) {
            const text = await res.text();
            throw new Error(`${res.status} ${text}`);
        }
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        // Extract filename from Content-Disposition header if available
        const contentDisposition = res.headers.get("Content-Disposition");
        if (contentDisposition) {
            const filenameMatch = contentDisposition.match(/filename="?([^"]+)"?/);
            if (filenameMatch) {
                a.download = filenameMatch[1];
            } else {
                a.download = `audit_logs_${new Date().toISOString().replace(/[:.]/g, "-")}.csv`;
            }
        } else {
            a.download = `audit_logs_${new Date().toISOString().replace(/[:.]/g, "-")}.csv`;
        }
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
    }
};


