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


export type SortField = "ts" | "actor" | "target_type" | "target_id" | "level"

export type SortDir = "asc" | "desc"