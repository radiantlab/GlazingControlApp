import React, { useEffect, useState } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type SensorReadingResponse } from "../api";

interface LiveGraphProps {
    sensorId: string;
    metric: string;
    color?: string;
    label?: string;
    height?: number;
    variant?: "card" | "embedded";
    yAxisLabel?: string;
    valueFormatter?: (value: number | undefined) => string;
}

export default function LiveGraph({ sensorId, metric, color = "#8884d8", label, height = 300, variant = "card", yAxisLabel, valueFormatter }: LiveGraphProps) {
    const [data, setData] = useState<SensorReadingResponse[]>([]);
    const [loading, setLoading] = useState(true);

    const loadData = async () => {
        try {
            const now = Date.now() / 1000;
            // Get last 1 hour of data
            const history = await api.getMetricHistory(sensorId, metric, now - 3600, now);
            // Sort by timestamp
            history.sort((a, b) => a.ts - b.ts);
            setData(history);
        } catch (err) {
            console.error("Failed to load graph data", err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadData();
        const interval = setInterval(loadData, 2000); // Poll every 2s
        return () => clearInterval(interval);
    }, [sensorId, metric]);

    const formatTime = (ts: number) => {
        const d = new Date(ts * 1000);
        return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    };

    const placeholder = (message: string) => (
        <div
            className={variant === "embedded" ? "live-graph-placeholder live-graph-placeholder-embedded" : "live-graph-placeholder"}
            style={{ height }}
        >
            {message}
        </div>
    );

    const formatTooltipValue = (value: number | undefined) => {
        if (valueFormatter) return valueFormatter(value);
        return value != null ? value.toFixed(1) : "N/A";
    };

    if (loading && !data.length) {
        return placeholder("Loading graph...");
    }

    if (!data.length) {
        return placeholder("No data available");
    }

    const chart = (
        <div className={variant === "embedded" ? "live-graph-chart live-graph-chart-embedded" : "live-graph-chart"} style={{ height }}>
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
                        tickFormatter={formatTime}
                        stroke="#888"
                        tick={{ fill: '#888' }}
                        minTickGap={50}
                        label={{
                            value: "Time",
                            position: "insideBottom",
                            offset: -18,
                            fill: "#888",
                        }}
                    />
                    <YAxis
                        stroke="#888"
                        tick={{ fill: '#888' }}
                        label={{
                            value: yAxisLabel || metric,
                            angle: -90,
                            position: "insideLeft",
                            fill: "#888",
                            style: { textAnchor: "middle" },
                        }}
                    />
                    <Tooltip
                        contentStyle={{ backgroundColor: '#222', border: '1px solid #444', borderRadius: 4, color: '#fff' }}
                        labelFormatter={(label) => new Date(label * 1000).toLocaleString()}
                        formatter={(value: number | undefined) => [formatTooltipValue(value), yAxisLabel || metric]}
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
