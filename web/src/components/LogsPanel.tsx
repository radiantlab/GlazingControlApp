import React, { useMemo, useState } from "react"
import type { AuditLogEntry } from "../api"

type LogsPanelProps = {
    isOpen: boolean
    onClose: () => void
    auditLogs: AuditLogEntry[]
    loading: boolean
    error: string | null
    onRefresh: () => void
    isMock: boolean
}

type SortField = "ts" | "actor" | "target_type" | "target_id" | "level"

export default function LogsPanel({
    isOpen,
    onClose,
    auditLogs,
    loading,
    error,
    onRefresh,
    isMock
}: LogsPanelProps) {
    const [activeTab, setActiveTab] = useState<"audit" | "sensors">("audit")
    const [typeFilter, setTypeFilter] = useState<"all" | "panel" | "group">("all")
    const [targetFilter, setTargetFilter] = useState("")
    const [resultFilter, setResultFilter] = useState("")
    const [sortField, setSortField] = useState<SortField>("ts")
    const [sortDir, setSortDir] = useState<"asc" | "desc">("desc")

    const filteredAuditLogs = useMemo(() => {
        let rows = auditLogs

        if (typeFilter !== "all") {
            rows = rows.filter(r => r.target_type === typeFilter)
        }

        if (targetFilter.trim()) {
            const needle = targetFilter.trim().toLowerCase()
            rows = rows.filter(
                r =>
                    r.target_id.toLowerCase().includes(needle) ||
                    r.applied_to.some(id => id.toLowerCase().includes(needle))
            )
        }

        if (resultFilter.trim()) {
            const needle = resultFilter.trim().toLowerCase()
            rows = rows.filter(r => r.result.toLowerCase().includes(needle))
        }

        const sorted = [...rows]
        sorted.sort((a, b) => {
            let av: number | string = a[sortField]
            let bv: number | string = b[sortField]

            if (sortField === "ts" || sortField === "level") {
                av = Number(av)
                bv = Number(bv)
                if (av < bv) return sortDir === "asc" ? -1 : 1
                if (av > bv) return sortDir === "asc" ? 1 : -1
                return 0
            }

            const as = String(av).toLowerCase()
            const bs = String(bv).toLowerCase()
            if (as < bs) return sortDir === "asc" ? -1 : 1
            if (as > bs) return sortDir === "asc" ? 1 : -1
            return 0
        })

        return sorted
    }, [auditLogs, typeFilter, targetFilter, resultFilter, sortField, sortDir])

    if (!isOpen) return null

    const toggleSort = (field: SortField) => {
        if (sortField === field) {
            setSortDir(prev => (prev === "asc" ? "desc" : "asc"))
        } else {
            setSortField(field)
            setSortDir("desc")
        }
    }

    const formatDateTime = (ts: number) => {
        if (!ts) return ""
        const d = new Date(ts * 1000)
        return d.toLocaleString()
    }

    const sortIndicator = (field: SortField) =>
        sortField === field ? (sortDir === "asc" ? "▲" : "▼") : ""

    return (
        <>
            <div className="side-panel-overlay" onClick={onClose} />
            <div
                className="logs-modal logs-panel"
                role="dialog"
                aria-modal="true"
                aria-labelledby="logs-modal-title"
                onClick={e => e.stopPropagation()}
            >
                <div className="logs-modal-header">
                    <h2 id="logs-modal-title">Logs</h2>
                    <button
                        className="logs-modal-close"
                        onClick={onClose}
                        aria-label="Close logs"
                    >
                        ✕
                    </button>
                </div>

                {/* tabs styled like manage side panel */}
                <div className="logs-modal-tabs">
                    <button
                        className={`side-panel-tab ${activeTab === "audit" ? "active" : ""}`}
                        onClick={() => setActiveTab("audit")}
                    >
                        Audit log
                    </button>
                    <button
                        className={`side-panel-tab ${activeTab === "sensors" ? "active" : ""}`}
                        onClick={() => setActiveTab("sensors")}
                    >
                        Sensor log
                    </button>
                </div>

                <div className="logs-panel-content">
                    {activeTab === "audit" && (
                        <div className="logs-section">
                            {isMock && (
                                <div className="logs-warning">
                                    Logs are not available in mock mode
                                </div>
                            )}

                            <div className="logs-toolbar">
                                <div className="logs-filters">
                                    <div className="form-group">
                                        <label>Type</label>
                                        <select
                                            value={typeFilter}
                                            onChange={e =>
                                                setTypeFilter(
                                                    e.target.value as "all" | "panel" | "group"
                                                )
                                            }
                                        >
                                            <option value="all">All</option>
                                            <option value="panel">Panels</option>
                                            <option value="group">Groups</option>
                                        </select>
                                    </div>

                                    <div className="form-group">
                                        <label>Target</label>
                                        <input
                                            type="text"
                                            value={targetFilter}
                                            onChange={e => setTargetFilter(e.target.value)}
                                            placeholder="Panel or group id"
                                        />
                                    </div>

                                    <div className="form-group">
                                        <label>Result</label>
                                        <input
                                            type="text"
                                            value={resultFilter}
                                            onChange={e => setResultFilter(e.target.value)}
                                            placeholder="Result text"
                                        />
                                    </div>
                                </div>

                                <div className="logs-actions">
                                    <button
                                        className="side-panel-secondary-btn logs-refresh-btn"
                                        onClick={onRefresh}
                                        disabled={loading}
                                    >
                                        {loading ? "Loading..." : "Refresh"}
                                    </button>
                                </div>
                            </div>

                            {error && <div className="logs-error">{error}</div>}

                            <div className="logs-table-wrapper">
                                <table className="logs-table">
                                    <thead>
                                        <tr>
                                            <th onClick={() => toggleSort("ts")}>
                                                <span>Time</span>
                                                <span className="logs-sort-indicator">
                                                    {sortIndicator("ts")}
                                                </span>
                                            </th>
                                            <th onClick={() => toggleSort("actor")}>
                                                <span>Actor</span>
                                                <span className="logs-sort-indicator">
                                                    {sortIndicator("actor")}
                                                </span>
                                            </th>
                                            <th onClick={() => toggleSort("target_type")}>
                                                <span>Type</span>
                                                <span className="logs-sort-indicator">
                                                    {sortIndicator("target_type")}
                                                </span>
                                            </th>
                                            <th onClick={() => toggleSort("target_id")}>
                                                <span>Target</span>
                                                <span className="logs-sort-indicator">
                                                    {sortIndicator("target_id")}
                                                </span>
                                            </th>
                                            <th onClick={() => toggleSort("level")}>
                                                <span>Level</span>
                                                <span className="logs-sort-indicator">
                                                    {sortIndicator("level")}
                                                </span>
                                            </th>
                                            <th>Applied to</th>
                                            <th>Result</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {filteredAuditLogs.length === 0 ? (
                                            <tr>
                                                <td colSpan={7} className="logs-empty">
                                                    {loading
                                                        ? "Loading logs..."
                                                        : "No audit entries match the current filters"}
                                                </td>
                                            </tr>
                                        ) : (
                                            filteredAuditLogs.map((row, idx) => (
                                                <tr key={`${row.ts}-${row.target_id}-${idx}`}>
                                                    <td className="logs-cell-time">
                                                        {formatDateTime(row.ts)}
                                                    </td>
                                                    <td>{row.actor}</td>
                                                    <td className="logs-cell-tag">
                                                        <span className={`logs-pill logs-pill-${row.target_type}`}>
                                                            {row.target_type}
                                                        </span>
                                                    </td>
                                                    <td>{row.target_id}</td>
                                                    <td>{row.level}</td>
                                                    <td className="logs-cell-applied">
                                                        {row.applied_to.join(", ")}
                                                    </td>
                                                    <td className="logs-cell-result">
                                                        {row.result}
                                                    </td>
                                                </tr>
                                            ))
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}

                    {activeTab === "sensors" && (
                        <div className="logs-section">
                            <h3>Sensor log</h3>
                            <p className="logs-sensors-placeholder">
                                Sensor logging is not implemented yet
                            </p>
                        </div>
                    )}
                </div>
            </div>
        </>
    )
}
