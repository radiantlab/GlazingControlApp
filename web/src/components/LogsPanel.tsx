import React, { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { api, type SensorInfo, type SensorLogEntry, type SensorSortField, type RoutineStatusResponse } from "../api"
import { sortSensorsForDisplay } from "../utils/sensorDisplay"

import { AuditLogEntry, SortField, SortDir } from "../types"

const InfoIcon = () => (
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" style={{ width: "14px", height: "14px", display: "inline-block", verticalAlign: "text-bottom", marginLeft: "4px", opacity: 0.6 }}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z" />
    </svg>
)

type SensorTimeFilterMode = "manual" | "latest"
type LatestTimeUnit = "minutes" | "hours" | "days"

type SensorTypeGroup = {
    key: string
    label: string
    rank: number
    sensors: SensorInfo[]
}

const latestUnitSeconds: Record<LatestTimeUnit, number> = {
    minutes: 60,
    hours: 60 * 60,
    days: 24 * 60 * 60,
}

const SENSOR_LOG_QUERY_LIMIT = 1000
const SENSOR_LOG_RENDER_LIMIT = 300
const SENSOR_LOG_AUTO_REFRESH_MS = 10000
const SENSOR_LOG_FILTER_DEBOUNCE_MS = 300

const logDateTimeFormatter = new Intl.DateTimeFormat(undefined, {
    dateStyle: "short",
    timeStyle: "medium",
})

type LoadSensorLogsOptions = {
    force?: boolean
    showLoading?: boolean
}

function formatLogDateTime(ts: number): string {
    if (!ts) return ""
    return logDateTimeFormatter.format(new Date(ts * 1000))
}

function areStringArraysEqual(a: string[], b: string[]): boolean {
    if (a === b) return true
    if (a.length !== b.length) return false
    return a.every((value, index) => value === b[index])
}

function areSensorLogRowsEqual(a: SensorLogEntry[], b: SensorLogEntry[]): boolean {
    if (a === b) return true
    if (a.length !== b.length) return false
    return a.every((row, index) => {
        const next = b[index]
        return row.sensor_id === next.sensor_id
            && row.sensor_kind === next.sensor_kind
            && row.sensor_label === next.sensor_label
            && row.metric === next.metric
            && row.value === next.value
            && row.ts === next.ts
    })
}

function titleCaseSensorKind(kind: string): string {
    return kind
        .replace(/[_-]+/g, " ")
        .split(" ")
        .filter(Boolean)
        .map(part => part.charAt(0).toUpperCase() + part.slice(1))
        .join(" ")
}

function sensorTypeForDisplay(sensor: SensorInfo): { key: string; label: string; rank: number } {
    const raw = `${sensor.kind} ${sensor.id} ${sensor.label || ""}`.toLowerCase()

    if (sensor.kind === "t10a" || raw.includes("t-10a") || raw.includes("t10a")) {
        return { key: "t10a", label: "T-10A", rank: 0 }
    }

    if (raw.includes("specbos")) {
        return { key: "specbos", label: "Specbos", rank: 2 }
    }

    if (raw.includes("spectrav")) {
        return { key: "spectrav", label: "Spectrav", rank: 1 }
    }

    if (sensor.kind === "eko_ms90_plus" || raw.includes("eko")) {
        return { key: "eko", label: "EKO", rank: 3 }
    }

    const fallback = sensor.kind || "unknown"
    return { key: fallback, label: titleCaseSensorKind(fallback), rank: 99 }
}

function formatLatestUnit(amount: number, unit: LatestTimeUnit): string {
    if (amount === 1) {
        return unit.slice(0, -1)
    }
    return unit
}

function sensorTypeLabelForLogRow(row: SensorLogEntry): string {
    return sensorTypeForDisplay({
        id: row.sensor_id,
        kind: row.sensor_kind || "",
        label: row.sensor_label || row.sensor_id,
        config: {},
    }).label
}

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
    onRoutineLinkClick?: (routineId: string) => void
    onViewSpectrum?: (sensorId: string, ts: number) => void
}

export default function LogsPanel({
    isOpen,
    onClose,
    auditLogs,
    loading,
    error,
    onRefresh,
    isMock,
    sensors,
    onRoutineLinkClick,
    onViewSpectrum
}: LogsPanelProps) {
    const [activeTab, setActiveTab] = useState<"audit" | "sensors" | "routines">("audit")
    const [typeFilter, setTypeFilter] = useState<"all" | "panel" | "group">("all")
    const [targetFilter, setTargetFilter] = useState("")
    const [resultFilter, setResultFilter] = useState("")
    const [startDate, setStartDate] = useState<string>("")
    const [endDate, setEndDate] = useState<string>("")
    const [sortField, setSortField] = useState<SortField>("ts")
    const [sortDir, setSortDir] = useState<SortDir>("desc")
    const [exporting, setExporting] = useState(false)

    const [activeSensorTypeKey, setActiveSensorTypeKey] = useState<string>("")
    const [sensorDeviceFilter, setSensorDeviceFilter] = useState<string>("")
    const [sensorMetricFilter, setSensorMetricFilter] = useState<string>("")
    const [sensorTimeFilterMode, setSensorTimeFilterMode] = useState<SensorTimeFilterMode>("latest")
    const [sensorStartDateTime, setSensorStartDateTime] = useState<string>("")
    const [sensorEndDateTime, setSensorEndDateTime] = useState<string>("")
    const [sensorLatestAmount, setSensorLatestAmount] = useState<string>("1")
    const [sensorLatestUnit, setSensorLatestUnit] = useState<LatestTimeUnit>("hours")
    const [sensorSortField, setSensorSortField] = useState<SensorSortField>("ts")
    const [sensorSortDir, setSensorSortDir] = useState<SortDir>("desc")
    const [sensorLogs, setSensorLogs] = useState<SensorLogEntry[]>([])
    const [sensorMetricOptions, setSensorMetricOptions] = useState<string[]>([])
    const [sensorShowAllRows, setSensorShowAllRows] = useState<boolean>(false)
    const [sensorLoading, setSensorLoading] = useState<boolean>(false)
    const [sensorError, setSensorError] = useState<string | null>(null)
    const [sensorExporting, setSensorExporting] = useState<boolean>(false)
    const sensorRequestInFlightRef = useRef(false)
    const sensorRequestIdRef = useRef(0)
    const sensorHasLoadedRef = useRef(false)

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

    const dateTimeStringToLocalTimestamp = (dateTimeString: string): number | undefined => {
        const date = new Date(dateTimeString)
        const seconds = date.getTime() / 1000
        if (!Number.isFinite(seconds)) return undefined
        return seconds
    }

    // Routines state
    const [routines, setRoutines] = useState<RoutineStatusResponse[]>([])
    const [routinesLoading, setRoutinesLoading] = useState(false)
    const [routinesError, setRoutinesError] = useState<string | null>(null)

    const loadRoutines = useCallback(async () => {
        if (isMock) {
            setRoutines([])
            setRoutinesError("Routine logs are not available in mock mode")
            return
        }
        try {
            setRoutinesLoading(true)
            setRoutinesError(null)
            const data = await api.getRoutines()
            setRoutines(data)
        } catch (err) {
            setRoutinesError(`Failed to load routines: ${String(err)}`)
        } finally {
            setRoutinesLoading(false)
        }
    }, [isMock])

    const sensorsSignature = useMemo(() => {
        return sensors
            .map(sensor => `${sensor.id}\u0001${sensor.kind}\u0001${sensor.label || ""}`)
            .sort()
            .join("\u0002")
    }, [sensors])

    const sensorTypeGroups = useMemo<SensorTypeGroup[]>(() => {
        const groups = new Map<string, SensorTypeGroup>()

        sortSensorsForDisplay(sensors).forEach(sensor => {
            const type = sensorTypeForDisplay(sensor)
            const existing = groups.get(type.key)
            if (existing) {
                existing.sensors.push(sensor)
                existing.rank = Math.min(existing.rank, type.rank)
            } else {
                groups.set(type.key, {
                    key: type.key,
                    label: type.label,
                    rank: type.rank,
                    sensors: [sensor],
                })
            }
        })

        return Array.from(groups.values()).sort((a, b) => {
            if (a.rank !== b.rank) return a.rank - b.rank
            return a.label.localeCompare(b.label, undefined, { numeric: true })
        })
    }, [sensorsSignature])

    const activeSensorGroup = useMemo(
        () => sensorTypeGroups.find(group => group.key === activeSensorTypeKey) || null,
        [activeSensorTypeKey, sensorTypeGroups]
    )

    const selectedSensorIds = useMemo(() => {
        if (!activeSensorGroup) return []
        if (sensorDeviceFilter) return [sensorDeviceFilter]
        return activeSensorGroup.sensors.map(sensor => sensor.id)
    }, [activeSensorGroup, sensorDeviceFilter])

    const selectedSensorIdsKey = useMemo(
        () => selectedSensorIds.join("\u0001"),
        [selectedSensorIds]
    )

    const displayedSensorMetricOptions = useMemo(() => {
        const options = new Set(sensorMetricOptions)
        if (sensorMetricFilter) options.add(sensorMetricFilter)
        return Array.from(options).sort((a, b) => a.localeCompare(b))
    }, [sensorMetricFilter, sensorMetricOptions])

    useEffect(() => {
        if (!sensorTypeGroups.length) {
            setActiveSensorTypeKey("")
            return
        }
        const exists = sensorTypeGroups.some(group => group.key === activeSensorTypeKey)
        if (!activeSensorTypeKey || !exists) {
            setActiveSensorTypeKey(sensorTypeGroups[0].key)
        }
    }, [activeSensorTypeKey, sensorTypeGroups])

    useEffect(() => {
        setSensorDeviceFilter("")
        setSensorMetricFilter("")
        setSensorMetricOptions([])
    }, [activeSensorTypeKey])

    useEffect(() => {
        if (!activeSensorGroup || !sensorDeviceFilter) return
        const exists = activeSensorGroup.sensors.some(sensor => sensor.id === sensorDeviceFilter)
        if (!exists) {
            setSensorDeviceFilter("")
        }
    }, [activeSensorGroup, sensorDeviceFilter])

    useEffect(() => {
        setSensorMetricFilter("")
        setSensorMetricOptions([])
    }, [sensorDeviceFilter])

    const getSensorTimeRange = useCallback((): { tsFrom?: number; tsTo?: number; error?: string } => {
        if (sensorTimeFilterMode === "latest") {
            const amount = Number(sensorLatestAmount)
            if (!Number.isFinite(amount) || amount <= 0) {
                return { error: "Enter a latest time range greater than 0." }
            }
            return {
                tsFrom: Date.now() / 1000 - amount * latestUnitSeconds[sensorLatestUnit],
            }
        }

        const tsFrom = sensorStartDateTime
            ? dateTimeStringToLocalTimestamp(sensorStartDateTime)
            : undefined
        const tsTo = sensorEndDateTime
            ? dateTimeStringToLocalTimestamp(sensorEndDateTime)
            : undefined

        if (sensorStartDateTime && tsFrom == null) {
            return { error: "Start date and time is invalid." }
        }
        if (sensorEndDateTime && tsTo == null) {
            return { error: "End date and time is invalid." }
        }
        if (tsFrom != null && tsTo != null && tsFrom > tsTo) {
            return { error: "Start date and time must be before end date and time." }
        }

        return { tsFrom, tsTo }
    }, [
        sensorEndDateTime,
        sensorLatestAmount,
        sensorLatestUnit,
        sensorStartDateTime,
        sensorTimeFilterMode,
    ])

    const loadSensorLogs = useCallback(async (options: LoadSensorLogsOptions = {}) => {
        const showLoading = options.showLoading ?? !sensorHasLoadedRef.current

        if (sensorRequestInFlightRef.current && !options.force) {
            return
        }

        const requestId = sensorRequestIdRef.current + 1
        sensorRequestIdRef.current = requestId
        sensorRequestInFlightRef.current = true

        if (isMock) {
            setSensorLogs(prev => (prev.length ? [] : prev))
            setSensorError("Sensor logs are not available in mock mode")
            setSensorLoading(false)
            sensorHasLoadedRef.current = true
            sensorRequestInFlightRef.current = false
            return
        }

        if (selectedSensorIds.length === 0) {
            setSensorLogs(prev => (prev.length ? [] : prev))
            setSensorError("No sensors are currently configured")
            setSensorLoading(false)
            sensorHasLoadedRef.current = true
            sensorRequestInFlightRef.current = false
            return
        }

        const metric = sensorMetricFilter.trim() || undefined
        const { tsFrom, tsTo, error } = getSensorTimeRange()
        if (error) {
            setSensorLogs(prev => (prev.length ? [] : prev))
            setSensorError(error)
            setSensorLoading(false)
            sensorHasLoadedRef.current = true
            sensorRequestInFlightRef.current = false
            return
        }

        try {
            if (showLoading) {
                setSensorLoading(true)
            }
            setSensorError(null)
            const rows = await api.getSensorLogs(
                SENSOR_LOG_QUERY_LIMIT,
                0,
                undefined,
                metric,
                tsFrom,
                tsTo,
                sensorSortField,
                sensorSortDir,
                { sensorIds: selectedSensorIds }
            )

            if (requestId !== sensorRequestIdRef.current) {
                return
            }

            setSensorLogs(prev => (areSensorLogRowsEqual(prev, rows) ? prev : rows))
            setSensorMetricOptions(prev => {
                const next = new Set(prev)
                rows.forEach(row => next.add(row.metric))
                if (metric) next.add(metric)
                const nextOptions = Array.from(next).sort((a, b) => a.localeCompare(b))
                return areStringArraysEqual(prev, nextOptions) ? prev : nextOptions
            })
            sensorHasLoadedRef.current = true
        } catch (err) {
            if (requestId === sensorRequestIdRef.current) {
                setSensorError(`Failed to load sensor logs: ${String(err)}`)
            }
        } finally {
            if (requestId === sensorRequestIdRef.current) {
                sensorRequestInFlightRef.current = false
                if (showLoading) {
                    setSensorLoading(false)
                }
            }
        }
    }, [
        isMock,
        selectedSensorIdsKey,
        sensorMetricFilter,
        getSensorTimeRange,
        sensorSortField,
        sensorSortDir
    ])

    useEffect(() => {
        sensorHasLoadedRef.current = false
        setSensorShowAllRows(false)
    }, [
        selectedSensorIdsKey,
        sensorMetricFilter,
        sensorTimeFilterMode,
        sensorStartDateTime,
        sensorEndDateTime,
        sensorLatestAmount,
        sensorLatestUnit,
        sensorSortField,
        sensorSortDir,
    ])

    useEffect(() => {
        if (!isOpen || activeTab !== "sensors") return

        const timeout = setTimeout(
            () => loadSensorLogs({ force: true, showLoading: true }),
            SENSOR_LOG_FILTER_DEBOUNCE_MS
        )
        return () => clearTimeout(timeout)
    }, [isOpen, activeTab, loadSensorLogs])

    useEffect(() => {
        if (!isOpen || activeTab !== "sensors" || isMock) return

        const interval = setInterval(
            () => loadSensorLogs({ showLoading: false }),
            SENSOR_LOG_AUTO_REFRESH_MS
        )
        return () => clearInterval(interval)
    }, [isOpen, activeTab, isMock, loadSensorLogs])

    useEffect(() => {
        if (!isOpen || activeTab !== "routines") return

        loadRoutines()
        const interval = setInterval(loadRoutines, 2000)
        return () => clearInterval(interval)
    }, [isOpen, activeTab, loadRoutines])

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

    const visibleSensorRows = useMemo(() => {
        const rows = sensorShowAllRows
            ? sensorLogs
            : sensorLogs.slice(0, SENSOR_LOG_RENDER_LIMIT)

        return rows.map((row, idx) => ({
            key: `${row.ts}-${row.sensor_id}-${row.metric}-${idx}`,
            row,
            time: formatLogDateTime(row.ts),
            sensorLabel: row.sensor_label || row.sensor_id,
            typeLabel: sensorTypeLabelForLogRow(row),
            value: row.value.toFixed(4),
            canViewSpectrum: row.sensor_kind === "jeti_spectraval" && Boolean(onViewSpectrum),
        }))
    }, [onViewSpectrum, sensorLogs, sensorShowAllRows])

    const hiddenSensorRowCount = Math.max(0, sensorLogs.length - visibleSensorRows.length)

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

    const formatDateTime = formatLogDateTime

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

        if (!activeSensorGroup || selectedSensorIds.length === 0) return

        const metric = sensorMetricFilter.trim() || undefined
        const { tsFrom, tsTo, error } = getSensorTimeRange()
        if (error) {
            setSensorError(error)
            return
        }

        setSensorExporting(true)
        try {
            await api.exportSensorLogs(
                100000,
                undefined,
                metric,
                tsFrom,
                tsTo,
                sensorSortField,
                sensorSortDir,
                { sensorIds: selectedSensorIds }
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
        setSensorStartDateTime("")
        setSensorEndDateTime("")
    }

    const showSensorDeviceFilter = Boolean(activeSensorGroup && activeSensorGroup.sensors.length > 1)
    const sensorDeviceFilterLabel = activeSensorGroup?.key === "t10a" ? "Head" : "Device"
    const allSensorDevicesLabel = activeSensorGroup?.key === "t10a" ? "All heads" : "All devices"
    const selectedSensor = activeSensorGroup?.sensors.find(sensor => sensor.id === sensorDeviceFilter)
    const activeSensorScopeLabel = selectedSensor
        ? (selectedSensor.label || selectedSensor.id)
        : activeSensorGroup
            ? `${allSensorDevicesLabel} in ${activeSensorGroup.label}`
            : "No sensor type"
    const latestAmountNumber = Number(sensorLatestAmount)
    const activeSensorTimeLabel = sensorTimeFilterMode === "latest"
        ? Number.isFinite(latestAmountNumber) && latestAmountNumber > 0
            ? `Latest ${sensorLatestAmount} ${formatLatestUnit(latestAmountNumber, sensorLatestUnit)}`
            : "Latest range"
        : sensorStartDateTime || sensorEndDateTime
            ? "Custom date range"
            : "All time"

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
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" style={{ width: "20px", height: "20px" }}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                        </svg>
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
                    <button
                        className={`side-panel-tab ${activeTab === "routines" ? "active" : ""}`}
                        onClick={() => setActiveTab("routines")}
                    >
                        Routine log
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
                                            <th onClick={() => toggleSort("ts")} title="When the action occurred">
                                                <span>Time <InfoIcon /></span>
                                                <span className="logs-sort-indicator">
                                                    {sortIndicator("ts")}
                                                </span>
                                            </th>
                                            <th onClick={() => toggleSort("actor")} title="The initiator of the action (e.g., manual, group, routine)">
                                                <span>Actor <InfoIcon /></span>
                                                <span className="logs-sort-indicator">
                                                    {sortIndicator("actor")}
                                                </span>
                                            </th>
                                            <th onClick={() => toggleSort("target_type")} title="Whether a single panel or a group was targeted">
                                                <span>Type <InfoIcon /></span>
                                                <span className="logs-sort-indicator">
                                                    {sortIndicator("target_type")}
                                                </span>
                                            </th>
                                            <th onClick={() => toggleSort("target_id")} title="The specific ID of the panel or group">
                                                <span>Target <InfoIcon /></span>
                                                <span className="logs-sort-indicator">
                                                    {sortIndicator("target_id")}
                                                </span>
                                            </th>
                                            <th onClick={() => toggleSort("level")} title="The applied tint level (0-100)">
                                                <span>Level <InfoIcon /></span>
                                                <span className="logs-sort-indicator">
                                                    {sortIndicator("level")}
                                                </span>
                                            </th>
                                            <th title="Panel IDs that were actually updated">Applied to <InfoIcon /></th>
                                            <th title="The resulting outcome of the action">Result <InfoIcon /></th>
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
                                                    <td>
                                                        {row.actor.startsWith("routine:") ? (
                                                            <button
                                                                className="hmi-link-btn"
                                                                onClick={() => {
                                                                    const routineId = row.actor.replace("routine:", "");
                                                                    if (onRoutineLinkClick) {
                                                                        onRoutineLinkClick(routineId);
                                                                    }
                                                                }}
                                                                title="View Routine"
                                                                style={{
                                                                    background: 'none',
                                                                    border: 'none',
                                                                    color: 'var(--txt-blue)',
                                                                    textDecoration: 'underline',
                                                                    cursor: 'pointer',
                                                                    padding: 0,
                                                                    font: 'inherit'
                                                                }}
                                                            >
                                                                {row.actor}
                                                            </button>
                                                        ) : (
                                                            row.actor
                                                        )}
                                                    </td>
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

                            {sensorTypeGroups.length > 0 && (
                                <div className="logs-sensor-type-tabs" role="tablist" aria-label="Sensor types">
                                    {sensorTypeGroups.map(group => (
                                        <button
                                            key={group.key}
                                            type="button"
                                            role="tab"
                                            aria-selected={activeSensorTypeKey === group.key}
                                            className={`logs-sensor-type-tab ${activeSensorTypeKey === group.key ? "active" : ""}`}
                                            onClick={() => setActiveSensorTypeKey(group.key)}
                                        >
                                            <span>{group.label}</span>
                                            <small>{group.sensors.length}</small>
                                        </button>
                                    ))}
                                </div>
                            )}

                            {sensorTypeGroups.length > 0 && (
                            <div className="logs-sensor-filter-panel">
                                <div className="logs-sensor-filter-grid">
                                    {showSensorDeviceFilter && (
                                        <div className="form-group">
                                            <label>{sensorDeviceFilterLabel}</label>
                                            <select
                                                value={sensorDeviceFilter}
                                                onChange={e => setSensorDeviceFilter(e.target.value)}
                                            >
                                                <option value="">{allSensorDevicesLabel}</option>
                                                {activeSensorGroup?.sensors.map(sensor => (
                                                    <option key={sensor.id} value={sensor.id}>
                                                        {sensor.label || sensor.id}
                                                    </option>
                                                ))}
                                            </select>
                                        </div>
                                    )}

                                    <div className="form-group">
                                        <label>Metric</label>
                                        <select
                                            value={sensorMetricFilter}
                                            onChange={e => setSensorMetricFilter(e.target.value)}
                                        >
                                            <option value="">All metrics</option>
                                            {displayedSensorMetricOptions.map(metric => (
                                                <option key={metric} value={metric}>
                                                    {metric}
                                                </option>
                                            ))}
                                        </select>
                                    </div>

                                    <div className="form-group logs-time-mode-group">
                                        <label>Time Filter</label>
                                        <div className="logs-filter-mode-toggle" role="group" aria-label="Sensor log time filter mode">
                                            <button
                                                type="button"
                                                className={sensorTimeFilterMode === "manual" ? "active" : ""}
                                                onClick={() => setSensorTimeFilterMode("manual")}
                                            >
                                                Date range
                                            </button>
                                            <button
                                                type="button"
                                                className={sensorTimeFilterMode === "latest" ? "active" : ""}
                                                onClick={() => setSensorTimeFilterMode("latest")}
                                            >
                                                Latest
                                            </button>
                                        </div>
                                    </div>

                                    <div className="form-group logs-date-time-range-group">
                                        <label>{sensorTimeFilterMode === "latest" ? "Latest Range" : "Date Range"}</label>
                                        {sensorTimeFilterMode === "latest" ? (
                                            <div className="logs-latest-inputs">
                                                <span>Latest</span>
                                                <input
                                                    type="number"
                                                    min="1"
                                                    step="1"
                                                    value={sensorLatestAmount}
                                                    onChange={e => setSensorLatestAmount(e.target.value)}
                                                    aria-label="Latest time amount"
                                                />
                                                <select
                                                    value={sensorLatestUnit}
                                                    onChange={e => setSensorLatestUnit(e.target.value as LatestTimeUnit)}
                                                    aria-label="Latest time unit"
                                                >
                                                    <option value="minutes">minutes</option>
                                                    <option value="hours">hours</option>
                                                    <option value="days">days</option>
                                                </select>
                                            </div>
                                        ) : (
                                            <div className="logs-date-time-inputs">
                                                <div className="logs-date-time-field">
                                                    <span>Start</span>
                                                    <input
                                                        type="datetime-local"
                                                        value={sensorStartDateTime}
                                                        onChange={e => setSensorStartDateTime(e.target.value)}
                                                        className="logs-date-input"
                                                    />
                                                </div>
                                                <span className="logs-date-separator">to</span>
                                                <div className="logs-date-time-field">
                                                    <span>End</span>
                                                    <input
                                                        type="datetime-local"
                                                        value={sensorEndDateTime}
                                                        onChange={e => setSensorEndDateTime(e.target.value)}
                                                        className="logs-date-input"
                                                        min={sensorStartDateTime || undefined}
                                                    />
                                                </div>
                                                {(sensorStartDateTime || sensorEndDateTime) && (
                                                    <button
                                                        className="logs-date-clear"
                                                        onClick={clearSensorDateFilters}
                                                        title="Clear date and time filters"
                                                    >
                                                        X
                                                    </button>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                </div>

                                <div className="logs-sensor-filter-footer">
                                    <div className="logs-sensor-active-state">
                                        <span className={`logs-status-dot ${sensorLoading ? "loading" : sensorError ? "error" : "ready"}`} />
                                        <span>{sensorLoading ? "Loading rows..." : `${sensorLogs.length.toLocaleString()} rows`}</span>
                                        <span>{activeSensorScopeLabel}</span>
                                        <span>{activeSensorTimeLabel}</span>
                                    </div>

                                    <div className="logs-actions">
                                        <button
                                            className="logs-action-btn logs-refresh-btn"
                                            onClick={() => loadSensorLogs({ force: true, showLoading: true })}
                                            disabled={sensorLoading || isMock || selectedSensorIds.length === 0}
                                        >
                                            <span>{sensorLoading ? "Loading..." : "Refresh"}</span>
                                        </button>
                                        <button
                                            className="logs-action-btn logs-export-btn"
                                            onClick={handleSensorExport}
                                            disabled={sensorExporting || sensorLoading || isMock || selectedSensorIds.length === 0}
                                            title={isMock ? "Export not available in mock mode" : "Export sensor logs to CSV"}
                                        >
                                            <span>{sensorExporting ? "Exporting..." : "Export CSV"}</span>
                                        </button>
                                    </div>
                                </div>
                            </div>
                            )}

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
                                                <span>Type</span>
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
                                            <th>Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {sensorLogs.length === 0 ? (
                                            <tr>
                                                <td colSpan={6} className="logs-empty">
                                                    {sensorLoading
                                                        ? "Loading sensor logs..."
                                                        : sensorTypeGroups.length === 0
                                                            ? "No sensor log data is available because no sensors are configured."
                                                            : `No readings for ${activeSensorScopeLabel} in ${activeSensorTimeLabel.toLowerCase()}.`}
                                                </td>
                                            </tr>
                                        ) : (
                                            <>
                                            {visibleSensorRows.map(displayRow => (
                                                <tr key={displayRow.key}>
                                                    <td className="logs-cell-time">{displayRow.time}</td>
                                                    <td>{displayRow.sensorLabel}</td>
                                                    <td>{displayRow.typeLabel}</td>
                                                    <td>{displayRow.row.metric}</td>
                                                    <td>{displayRow.value}</td>
                                                    <td>
                                                        {displayRow.canViewSpectrum && onViewSpectrum ? (
                                                            <button
                                                                className="hmi-link-btn logs-spectrogram-btn"
                                                                onClick={() => onViewSpectrum(displayRow.row.sensor_id, displayRow.row.ts)}
                                                                title="View Spectrogram at this timestamp"
                                                            >
                                                                <span>Spectrogram</span>
                                                            </button>
                                                        ) : (
                                                            <span className="logs-cell-muted">-</span>
                                                        )}
                                                    </td>
                                                </tr>
                                            ))}
                                            {hiddenSensorRowCount > 0 && (
                                                <tr>
                                                    <td colSpan={6} className="logs-empty">
                                                        Showing {visibleSensorRows.length.toLocaleString()} of {sensorLogs.length.toLocaleString()} rows.{" "}
                                                        <button
                                                            className="logs-inline-btn"
                                                            type="button"
                                                            onClick={() => setSensorShowAllRows(true)}
                                                        >
                                                            Show all fetched rows
                                                        </button>
                                                    </td>
                                                </tr>
                                            )}
                                            </>
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}

                    {activeTab === "routines" && (
                        <div className="logs-section">
                            {isMock && (
                                <div className="logs-warning">
                                    Routine logs are not available in mock mode
                                </div>
                            )}

                            <div className="logs-toolbar">
                                <div className="logs-actions" style={{ marginLeft: "auto" }}>
                                    <button
                                        className="logs-action-btn logs-refresh-btn"
                                        onClick={loadRoutines}
                                        disabled={routinesLoading || isMock}
                                    >
                                        <span>{routinesLoading ? "Loading..." : "Refresh"}</span>
                                    </button>
                                </div>
                            </div>

                            {routinesError && <div className="logs-error">{routinesError}</div>}

                            <div className="logs-table-wrapper">
                                <table className="logs-table">
                                    <thead>
                                        <tr>
                                            <th>Name</th>
                                            <th>Mode</th>
                                            <th>Status</th>
                                            <th>Run / Ended At</th>
                                            <th>Logs Summary</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {routines.filter(r => r.status === "done" || r.status === "error" || r.status === "stopped").length === 0 ? (
                                            <tr>
                                                <td colSpan={5} className="logs-empty">
                                                    {routinesLoading ? "Loading routines..." : "No past routines found"}
                                                </td>
                                            </tr>
                                        ) : (
                                            routines
                                                .filter(r => r.status === "done" || r.status === "error" || r.status === "stopped")
                                                .sort((a, b) => (b.run_at_ts || 0) - (a.run_at_ts || 0))
                                                .map(r => {
                                                    const lastLog = r.logs && r.logs.length > 0 ? r.logs[r.logs.length - 1] : "No logs";
                                                    const hasError = r.status === "error" || lastLog.includes("❌");
                                                    const hasSuccess = r.status === "done" || lastLog.includes("✅");

                                                    return (
                                                        <tr key={r.id}>
                                                            <td style={{ fontWeight: 600 }}>
                                                                <button
                                                                    className="hmi-link-btn"
                                                                    onClick={() => {
                                                                        if (onRoutineLinkClick) {
                                                                            onRoutineLinkClick(r.id);
                                                                        }
                                                                    }}
                                                                    title="View Routine code and logs"
                                                                    style={{
                                                                        background: 'none',
                                                                        border: 'none',
                                                                        color: 'var(--txt-blue)',
                                                                        textDecoration: 'underline',
                                                                        cursor: 'pointer',
                                                                        padding: 0,
                                                                        font: 'inherit'
                                                                    }}
                                                                >
                                                                    {r.name}
                                                                </button>
                                                            </td>
                                                            <td style={{ color: "var(--hmi-text-muted)", fontSize: "12px" }}>{r.mode}</td>
                                                            <td>
                                                                <span className={`routine-status-badge routine-status-${r.status}`} style={{ margin: 0, zoom: 0.85 }}>
                                                                    ● {r.status}
                                                                </span>
                                                            </td>
                                                            <td style={{ fontSize: "12px", color: "var(--hmi-text-muted)" }}>
                                                                {r.run_at_ts ? formatDateTime(r.run_at_ts) : "-"}
                                                            </td>
                                                            <td style={{
                                                                color: hasError ? "var(--txt-red)" : hasSuccess ? "var(--txt-green)" : "inherit",
                                                                fontSize: "13px",
                                                                maxWidth: "400px",
                                                                whiteSpace: "nowrap",
                                                                overflow: "hidden",
                                                                textOverflow: "ellipsis"
                                                            }} title={lastLog}>
                                                                {lastLog}
                                                            </td>
                                                        </tr>
                                                    )
                                                })
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
