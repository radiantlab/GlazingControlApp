import React, { useMemo, useState } from "react"
import type { AuditLogEntry } from "../api"
import { api } from "../api"

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
    const [startDate, setStartDate] = useState<string>("")
    const [endDate, setEndDate] = useState<string>("")
    const [sortField, setSortField] = useState<SortField>("ts")
    const [sortDir, setSortDir] = useState<"asc" | "desc">("desc")
    const [exporting, setExporting] = useState(false)

    // Helper function to convert a date string (YYYY-MM-DD) to UTC timestamp
    // Parses the date string as a local date (start/end of day in user's timezone),
    // then converts to UTC timestamp. This ensures filtering matches what users see
    // in toLocaleString() display, where entries are shown in their local timezone.
    const dateStringToLocalTimestamp = (dateString: string, isEndOfDay: boolean = false): number => {
        // Parse date string components and create a Date object representing
        // start/end of day in the user's local timezone
        const [year, month, day] = dateString.split('-').map(Number)
        const date = new Date(year, month - 1, day, isEndOfDay ? 23 : 0, isEndOfDay ? 59 : 0, isEndOfDay ? 59 : 0, isEndOfDay ? 999 : 0)
        // getTime() returns UTC milliseconds, convert to seconds
        const seconds = date.getTime() / 1000
        if (isEndOfDay) {
            // For end of day, return the full seconds value (including fractional milliseconds)
            // This ensures entries like 23:59:59.5 are included (r.ts <= endTs)
            return seconds
        }
        // For start of day, use floor to get the exact start of the day (00:00:00.000)
        return Math.floor(seconds)
    }

    const filteredAuditLogs = useMemo(() => {
        let rows = auditLogs

        // Date range filtering - convert local date strings to UTC timestamps
        // This ensures the filter matches entries displayed via toLocaleString()
        if (startDate) {
            const startTs = dateStringToLocalTimestamp(startDate, false)
            rows = rows.filter(r => r.ts >= startTs)
        }
        if (endDate) {
            const endTs = dateStringToLocalTimestamp(endDate, true)
            rows = rows.filter(r => r.ts <= endTs)
        }

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
    }, [auditLogs, typeFilter, targetFilter, resultFilter, startDate, endDate, sortField, sortDir])

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

    const handleExport = async () => {
        if (exporting || isMock) return
        setExporting(true)
        try {
            // Trim filter values to match local filtering logic (whitespace-only filters are ignored)
            const trimmedTargetFilter = targetFilter.trim() || undefined
            const trimmedResultFilter = resultFilter.trim() || undefined
            
            await api.exportAuditLogs(
                10000,
                startDate || undefined,
                endDate || undefined,
                typeFilter !== "all" ? typeFilter : undefined,
                trimmedTargetFilter,
                trimmedResultFilter
            )
        } catch (err) {
            console.error("Failed to export audit logs:", err)
            alert("Failed to export audit logs. Please try again.")
        } finally {
            setExporting(false)
        }
    }

    const clearDateFilters = () => {
        setStartDate("")
        setEndDate("")
    }

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
                                    <div className="form-group logs-date-range-group">
                                        <label>Date Range</label>
                                        <div className="logs-date-inputs">
                                            <input
                                                type="date"
                                                value={startDate}
                                                onChange={e => setStartDate(e.target.value)}
                                                className="logs-date-input"
                                                placeholder="Start date"
                                            />
                                            <span className="logs-date-separator">to</span>
                                            <input
                                                type="date"
                                                value={endDate}
                                                onChange={e => setEndDate(e.target.value)}
                                                className="logs-date-input"
                                                placeholder="End date"
                                                min={startDate || undefined}
                                            />
                                            {(startDate || endDate) && (
                                                <button
                                                    className="logs-date-clear"
                                                    onClick={clearDateFilters}
                                                    title="Clear date filters"
                                                >
                                                    ✕
                                                </button>
                                            )}
                                        </div>
                                    </div>

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
                                        className="logs-action-btn logs-refresh-btn"
                                        onClick={onRefresh}
                                        disabled={loading}
                                    >
                                        <span className="logs-btn-icon">↻</span>
                                        <span>{loading ? "Loading..." : "Refresh"}</span>
                                    </button>
                                    <button
                                        className="logs-action-btn logs-export-btn"
                                        onClick={handleExport}
                                        disabled={exporting || loading || isMock}
                                        title={isMock ? "Export not available in mock mode" : "Export all audit logs to CSV"}
                                    >
                                        <span className="logs-btn-icon">⬇</span>
                                        <span>{exporting ? "Exporting..." : "Export CSV"}</span>
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
