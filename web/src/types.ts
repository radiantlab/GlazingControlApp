export type Panel = {
    id: string;
    name: string;
    group_id?: string | null;
    level: number;
    last_change_ts: number;
};

export type GroupLayoutItem = {
    panel_id: string;
    row: number;
    column: number;
};

export type GroupLayoutDivider = {
    row: number;
    column: number;
};

export type GroupLayoutDividers = {
    vertical: GroupLayoutDivider[];
    horizontal: GroupLayoutDivider[];
};

export type GroupLayout = {
    columns: number;
    rows?: number | null;
    items: GroupLayoutItem[];
    dividers?: GroupLayoutDividers | null;
};

export type Group = {
    id: string;
    name: string;
    member_ids: string[];
    layout?: GroupLayout | null;
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
