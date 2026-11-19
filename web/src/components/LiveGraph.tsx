import React, { useEffect, useState } from "react";
import {
    Area,
    AreaChart,
    CartesianGrid,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from "recharts";
import { api, type SensorReadingResponse } from "../api";
import type { HistoricalRange } from "./HistoricalTimePicker";

interface LiveGraphProps {
    sensorId: string;
    metric: string;
    color?: string;
    label?: string;
    height?: number;
    variant?: "card" | "embedded";
    yAxisLabel?: string;
    valueFormatter?: (value: number | undefined) => string;
    /** Applied historical range in Unix seconds; omit for live mode. */
    range?: HistoricalRange;
    /** End of the last-reading window for an offline sensor. */
    endTs?: number;
}

// Recharts types tooltip labels and values loosely (ReactNode, number | string |
// array). Timestamps and readings are numbers; accept numeric strings too, and
// treat anything else as missing.
function toFiniteNumber(value: unknown): number | undefined {
    const parsed =
        typeof value === "number"
            ? value
            : typeof value === "string" && value.trim() !== ""
              ? Number(value)
              : Number.NaN;
    return Number.isFinite(parsed) ? parsed : undefined;
}

function LiveGraph({
    sensorId,
    metric,
    color = "#8884d8",
    label,
    height = 300,
    variant = "card",
    yAxisLabel,
    valueFormatter,
    range,
    endTs,
}: LiveGraphProps) {
    const [data, setData] = useState<SensorReadingResponse[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(false);

    useEffect(() => {
        let active = true;
        let inFlight = false;
        setLoading(true);
        setError(false);
        const loadData = async () => {
            if (inFlight) return;
            inFlight = true;
            try {
                const end = range?.endTs ?? endTs ?? Date.now() / 1000;
                const history = await api.getMetricHistory(
                    sensorId,
                    metric,
                    range?.startTs ?? end - 3600,
                    end,
                );
                // Ignore responses belonging to a previous range, metric or unmounted graph.
                if (active) {
                    setData([...history].sort((a, b) => a.ts - b.ts));
                    setError(false);
                }
            } catch {
                if (active) setError(true);
            } finally {
                if (active) setLoading(false);
                inFlight = false;
            }
        };

        loadData();
        const interval = !range && endTs == null ? setInterval(loadData, 2000) : undefined;
        return () => {
            active = false;
            clearInterval(interval);
        };
    }, [sensorId, metric, range, endTs]);

    const formatTime = (ts: number) => {
        const d = new Date(ts * 1000);
        return range
            ? d.toLocaleString([], {
                  month: "short",
                  day: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
              })
            : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    };

    const placeholder = (message: string, failed = false) => (
        <div
            className={
                variant === "embedded"
                    ? "live-graph-placeholder live-graph-placeholder-embedded"
                    : "live-graph-placeholder"
            }
            style={{ height }}
        >
            <p role={failed ? "alert" : "status"}>{message}</p>
        </div>
    );

    const formatTooltipValue = (value: number | undefined) => {
        if (valueFormatter) return valueFormatter(value);
        return value != null ? value.toFixed(1) : "N/A";
    };

    if (loading) {
        return placeholder("Loading graph...");
    }

    if (error)
        return placeholder("Unable to load graph data. Apply a time range to try again.", true);

    if (!data.length) {
        return placeholder("No data available");
    }

    const chart = (
        <div
            className={
                variant === "embedded"
                    ? "live-graph-chart live-graph-chart-embedded"
                    : "live-graph-chart"
            }
            style={{ height }}
        >
            <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data} margin={{ top: 10, right: 20, left: 34, bottom: 26 }}>
                    <defs>
                        <linearGradient id={`color${sensorId}`} x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor={color} stopOpacity={0.8} />
                            <stop offset="95%" stopColor={color} stopOpacity={0} />
                        </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#333" />
                    <XAxis
                        dataKey="ts"
                        type="number"
                        domain={[range?.startTs ?? "dataMin", range?.endTs ?? "dataMax"]}
                        tickFormatter={formatTime}
                        stroke="#888"
                        tick={{ fill: "#888" }}
                        minTickGap={50}
                        label={{
                            value: "Time (browser local)",
                            position: "insideBottom",
                            offset: -18,
                            fill: "#888",
                        }}
                    />
                    <YAxis
                        stroke="#888"
                        tick={{ fill: "#888" }}
                        label={{
                            value: yAxisLabel || metric,
                            angle: -90,
                            position: "insideLeft",
                            fill: "#888",
                            style: { textAnchor: "middle" },
                        }}
                    />
                    <Tooltip
                        contentStyle={{
                            backgroundColor: "#222",
                            border: "1px solid #444",
                            borderRadius: 4,
                            color: "#fff",
                        }}
                        labelFormatter={(label) => {
                            const ts = toFiniteNumber(label);
                            return ts === undefined
                                ? ""
                                : new Date(ts * 1000).toLocaleString(undefined, {
                                      timeZoneName: "short",
                                  });
                        }}
                        formatter={(value) => [
                            formatTooltipValue(toFiniteNumber(value)),
                            yAxisLabel || metric,
                        ]}
                    />
                    <Area
                        type="monotone"
                        dataKey="value"
                        stroke={color}
                        fillOpacity={1}
                        fill={`url(#color${sensorId})`}
                        animationDuration={500}
                    />
                </AreaChart>
            </ResponsiveContainer>
        </div>
    );

    if (variant === "embedded") {
        return chart;
    }

    return (
        <div className="room-section live-graph-card" style={{ marginTop: 20 }}>
            <div className="room-header">
                <h2 className="room-title">{label || `${sensorId} - ${metric}`}</h2>
            </div>
            {chart}
        </div>
    );
}

export default React.memo(LiveGraph, (prevProps, nextProps) => {
    return (
        prevProps.sensorId === nextProps.sensorId &&
        prevProps.metric === nextProps.metric &&
        prevProps.color === nextProps.color &&
        prevProps.label === nextProps.label &&
        prevProps.height === nextProps.height &&
        prevProps.variant === nextProps.variant &&
        prevProps.yAxisLabel === nextProps.yAxisLabel &&
        prevProps.range === nextProps.range &&
        prevProps.endTs === nextProps.endTs
    );
});
