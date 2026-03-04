import React, { useCallback, useEffect, useMemo, useState } from "react"
import { api, type SensorInfo, type SensorLogEntry, type SensorSortField } from "../api"

import { AuditLogEntry, SortField, SortDir } from "../types"

// local
type LogsPanelProps = {
    isOpen: boolean
    onClose: () => void
    auditLogs: AuditLogEntry[]
    loading: boolean
    error: string | null
    onRefresh: () => void
    isMock: boolean
    sensors: SensorInfo[]
}

export default function LogsPanel({
    isOpen,
    onClose,
    auditLogs,
    loading,
    error,
    onRefresh,
    isMock,
    sensors
}: LogsPanelProps) {
    const [activeTab, setActiveTab] = useState<"audit" | "sensors">("audit")
    const [typeFilter, setTypeFilter] = useState<"all" | "panel" | "group">("all")
    const [targetFilter, setTargetFilter] = useState("")
    const [resultFilter, setResultFilter] = useState("")
    const [startDate, setStartDate] = useState<string>("")
    const [endDate, setEndDate] = useState<string>("")
    const [sortField, setSortField] = useState<SortField>("ts")
    const [sortDir, setSortDir] = useState<SortDir>("desc")
    const [exporting, setExporting] = useState(false)

    const [activeSensorId, setActiveSensorId] = useState<string>("")
    const [sensorMetricFilter, setSensorMetricFilter] = useState<string>("")
    const [sensorStartDate, setSensorStartDate] = useState<string>("")
    const [sensorEndDate, setSensorEndDate] = useState<string>("")
    const [sensorSortField, setSensorSortField] = useState<SensorSortField>("ts")
    const [sensorSortDir, setSensorSortDir] = useState<SortDir>("desc")
    const [sensorLogs, setSensorLogs] = useState<SensorLogEntry[]>([])
    const [sensorLoading, setSensorLoading] = useState<boolean>(false)
    const [sensorError, setSensorError] = useState<string | null>(null)
    const [sensorExporting, setSensorExporting] = useState<boolean>(false)

    // Helper function to convert a date string (YYYY-MM-DD) to UTC timestamp
    // Parses the date string as a local date (start/end of day in user's timezone),
    // then converts to UTC timestamp. This ensures filtering matches what users see
    // in toLocaleString() display, where entries are shown in their local timezone.
    const dateStringToLocalTimestamp = (dateString: string, isEndOfDay: boolean = false): number => {
        const [year, month, day] = dateString.split('-').map(Number)
        const date = new Date(year, month - 1, day, isEndOfDay ? 23 : 0, isEndOfDay ? 59 : 0, isEndOfDay ? 59 : 0, isEndOfDay ? 999 : 0)
        const seconds = date.getTime() / 1000
        if (isEndOfDay) {
            return seconds
        }
        return Math.floor(seconds)
    }

    useEffect(() => {
        if (!sensors.length) {
            setActiveSensorId("")
            return
        }
        const exists = sensors.some(sensor => sensor.id === activeSensorId)
        if (!activeSensorId || !exists) {
            setActiveSensorId(sensors[0].id)
        }
    }, [activeSensorId, sensors])

    useEffect(() => {
        // Reset metric filter when switching sensors to avoid carrying a stale metric
        // that does not exist on the newly selected sensor.
        setSensorMetricFilter("")
    }, [activeSensorId])

    const loadSensorLogs = useCallback(async () => {
        if (isMock) {
            setSensorLogs([])
            setSensorError("Sensor logs are not available in mock mode")
            return
        }

        if (!activeSensorId) {
            setSensorLogs([])
            setSensorError("No sensors are currently configured")
            return
        }

        const sensorId = activeSensorId
        const metric = sensorMetricFilter.trim() || undefined
        const tsFrom = sensorStartDate ? dateStringToLocalTimestamp(sensorStartDate, false) : undefined
        const tsTo = sensorEndDate ? dateStringToLocalTimestamp(sensorEndDate, true) : undefined

        try {
            setSensorLoading(true)
            setSensorError(null)
            const rows = await api.getSensorLogs(
                1000,
                0,
                sensorId,
                metric,
                tsFrom,
                tsTo,
                sensorSortField,
                sensorSortDir
            )
            setSensorLogs(rows)
        } catch (err) {
            setSensorError(`Failed to load sensor logs: ${String(err)}`)
        } finally {
            setSensorLoading(false)
        }
    }, [
        isMock,
        activeSensorId,
        sensorMetricFilter,
        sensorStartDate,
        sensorEndDate,
        sensorSortField,
        sensorSortDir
    ])

    useEffect(() => {
        if (!isOpen || activeTab !== "sensors") return

        loadSensorLogs()
        const interval = setInterval(loadSensorLogs, 2000)
        return () => clearInterval(interval)
    }, [isOpen, activeTab, loadSensorLogs])

    const filteredAuditLogs = useMemo(() => {
        let rows = auditLogs

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

    const sensorMetricOptions = useMemo(() => {
        return Array.from(new Set(sensorLogs.map(row => row.metric))).sort((a, b) => a.localeCompare(b))
    }, [sensorLogs])

    useEffect(() => {
        if (sensorMetricFilter && !sensorMetricOptions.includes(sensorMetricFilter)) {
            setSensorMetricFilter("")
        }
    }, [sensorMetricFilter, sensorMetricOptions])

    if (!isOpen) return null

    const toggleSort = (field: SortField) => {
        if (sortField === field) {
            setSortDir(prev => (prev === "asc" ? "desc" : "asc"))
        } else {
            setSortField(field)
            setSortDir("desc")
        }
    }

    const toggleSensorSort = (field: SensorSortField) => {
        if (sensorSortField === field) {
            setSensorSortDir(prev => (prev === "asc" ? "desc" : "asc"))
        } else {
            setSensorSortField(field)
            setSensorSortDir("desc")
        }
    }

    const formatDateTime = (ts: number) => {
        if (!ts) return ""
        const d = new Date(ts * 1000)
        return d.toLocaleString()
    }

    const sortIndicator = (field: SortField) =>
        sortField === field ? (sortDir === "asc" ? "^" : "v") : ""

    const sensorSortIndicator = (field: SensorSortField) =>
        sensorSortField === field ? (sensorSortDir === "asc" ? "^" : "v") : ""

    const handleExport = async () => {
        if (exporting || isMock) return
        setExporting(true)
        try {
            const trimmedTargetFilter = targetFilter.trim() || undefined
            const trimmedResultFilter = resultFilter.trim() || undefined

            await api.exportAuditLogs(
                10000,
                startDate || undefined,
                endDate || undefined,
                typeFilter !== "all" ? typeFilter : undefined,
                trimmedTargetFilter,
                trimmedResultFilter,
                sortField,
                sortDir
            )
        } catch (err) {
            console.error("Failed to export audit logs:", err)
            alert("Failed to export audit logs. Please try again.")
        } finally {
            setExporting(false)
        }
    }

    const handleSensorExport = async () => {
        if (sensorExporting || isMock) return

        if (!activeSensorId) return

        const sensorId = activeSensorId
        const metric = sensorMetricFilter.trim() || undefined
        const tsFrom = sensorStartDate ? dateStringToLocalTimestamp(sensorStartDate, false) : undefined
        const tsTo = sensorEndDate ? dateStringToLocalTimestamp(sensorEndDate, true) : undefined

        setSensorExporting(true)
        try {
            await api.exportSensorLogs(
                100000,
                sensorId,
                metric,
                tsFrom,
                tsTo,
                sensorSortField,
                sensorSortDir
            )
        } catch (err) {
            console.error("Failed to export sensor logs:", err)
            alert("Failed to export sensor logs. Please try again.")
        } finally {
            setSensorExporting(false)
        }
    }

    const clearDateFilters = () => {
        setStartDate("")
        setEndDate("")
    }

    const clearSensorDateFilters = () => {
        setSensorStartDate("")
        setSensorEndDate("")
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
                        X
                    </button>
                </div>

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
                                                    X
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
                                        <span>{loading ? "Loading..." : "Refresh"}</span>
                                    </button>
                                    <button
                                        className="logs-action-btn logs-export-btn"
                                        onClick={handleExport}
                                        disabled={exporting || loading || isMock}
                                        title={isMock ? "Export not available in mock mode" : "Export all audit logs to CSV"}
                                    >
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
                            {isMock && (
                                <div className="logs-warning">
                                    Sensor logs are not available in mock mode
                                </div>
                            )}

                            <div className="logs-sensor-tabs">
                                {sensors.map(sensor => (
                                    <button
                                        key={sensor.id}
                                        className={`side-panel-tab ${activeSensorId === sensor.id ? "active" : ""}`}
                                        onClick={() => setActiveSensorId(sensor.id)}
                                        title={`${sensor.label} (${sensor.kind})`}
                                    >
                                        {sensor.label || sensor.id}
                                    </button>
                                ))}
                            </div>

                            <div className="logs-toolbar">
                                <div className="logs-filters">
                                    <div className="form-group logs-date-range-group">
                                        <label>Date Range</label>
                                        <div className="logs-date-inputs">
                                            <input
                                                type="date"
                                                value={sensorStartDate}
                                                onChange={e => setSensorStartDate(e.target.value)}
                                                className="logs-date-input"
                                                placeholder="Start date"
                                            />
                                            <span className="logs-date-separator">to</span>
                                            <input
                                                type="date"
                                                value={sensorEndDate}
                                                onChange={e => setSensorEndDate(e.target.value)}
                                                className="logs-date-input"
                                                placeholder="End date"
                                                min={sensorStartDate || undefined}
                                            />
                                            {(sensorStartDate || sensorEndDate) && (
                                                <button
                                                    className="logs-date-clear"
                                                    onClick={clearSensorDateFilters}
                                                    title="Clear date filters"
                                                >
                                                    X
                                                </button>
                                            )}
                                        </div>
                                    </div>

                                    <div className="form-group">
                                        <label>Metric</label>
                                        <select
                                            value={sensorMetricFilter}
                                            onChange={e => setSensorMetricFilter(e.target.value)}
                                        >
                                            <option value="">All metrics</option>
                                            {sensorMetricOptions.map(metric => (
                                                <option key={metric} value={metric}>
                                                    {metric}
                                                </option>
                                            ))}
                                        </select>
                                    </div>
                                </div>

                                <div className="logs-actions">
                                    <button
                                        className="logs-action-btn logs-refresh-btn"
                                        onClick={loadSensorLogs}
                                        disabled={sensorLoading}
                                    >
                                        <span>{sensorLoading ? "Loading..." : "Refresh"}</span>
                                    </button>
                                    <button
                                        className="logs-action-btn logs-export-btn"
                                        onClick={handleSensorExport}
                                        disabled={sensorExporting || sensorLoading || isMock}
                                        title={isMock ? "Export not available in mock mode" : "Export sensor logs to CSV"}
                                    >
                                        <span>{sensorExporting ? "Exporting..." : "Export CSV"}</span>
                                    </button>
                                </div>
                            </div>

                            {sensors.length === 0 && (
                                <div className="logs-warning">No sensors are currently configured.</div>
                            )}

                            {sensorError && <div className="logs-error">{sensorError}</div>}

                            <div className="logs-table-wrapper">
                                <table className="logs-table">
                                    <thead>
                                        <tr>
                                            <th onClick={() => toggleSensorSort("ts")}>
                                                <span>Time</span>
                                                <span className="logs-sort-indicator">{sensorSortIndicator("ts")}</span>
                                            </th>
                                            <th onClick={() => toggleSensorSort("sensor_id")}>
                                                <span>Sensor</span>
                                                <span className="logs-sort-indicator">{sensorSortIndicator("sensor_id")}</span>
                                            </th>
                                            <th onClick={() => toggleSensorSort("sensor_kind")}>
                                                <span>Kind</span>
                                                <span className="logs-sort-indicator">{sensorSortIndicator("sensor_kind")}</span>
                                            </th>
                                            <th onClick={() => toggleSensorSort("metric")}>
                                                <span>Metric</span>
                                                <span className="logs-sort-indicator">{sensorSortIndicator("metric")}</span>
                                            </th>
                                            <th onClick={() => toggleSensorSort("value")}>
                                                <span>Value</span>
                                                <span className="logs-sort-indicator">{sensorSortIndicator("value")}</span>
                                            </th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {sensorLogs.length === 0 ? (
                                            <tr>
                                                <td colSpan={5} className="logs-empty">
                                                    {sensorLoading
                                                        ? "Loading sensor logs..."
                                                        : "No sensor readings match the current filters"}
                                                </td>
                                            </tr>
                                        ) : (
                                            sensorLogs.map((row, idx) => (
                                                <tr key={`${row.ts}-${row.sensor_id}-${row.metric}-${idx}`}>
                                                    <td className="logs-cell-time">{formatDateTime(row.ts)}</td>
                                                    <td>{row.sensor_label || row.sensor_id}</td>
                                                    <td>{row.sensor_kind || "-"}</td>
                                                    <td>{row.metric}</td>
                                                    <td>{row.value.toFixed(4)}</td>
                                                </tr>
                                            ))
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </>
    )
}
