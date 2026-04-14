import React, { useEffect, useState, useRef } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type SensorReadingResponse } from "../api";

interface LiveGraphProps {
    sensorId: string;
    metric: string;
    color?: string;
    label?: string;
    height?: number;
}

export default function LiveGraph({ sensorId, metric, color = "#8884d8", label, height = 300 }: LiveGraphProps) {
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

    if (loading && !data.length) {
        return <div style={{ height, display: "flex", alignItems: "center", justifyContent: "center", color: "#666" }}>Loading graph...</div>;
    }

    if (!data.length) {
        return <div style={{ height, display: "flex", alignItems: "center", justifyContent: "center", color: "#666" }}>No data available</div>;
    }

    const formatTime = (ts: number) => {
        const d = new Date(ts * 1000);
        return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    };

    return (
        <div className="room-section" style={{ marginTop: 20 }}>
            <div className="room-header">
                <h2 className="room-title">{label || `${sensorId} - ${metric}`}</h2>
            </div>
            <div style={{ height, padding: "10px 20px 20px 0" }}>
                <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={data}>
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
                        />
                        <YAxis
                            stroke="#888"
                            tick={{ fill: '#888' }}
                        />
                        <Tooltip
                            contentStyle={{ backgroundColor: '#222', border: '1px solid #444', borderRadius: 4, color: '#fff' }}
                            labelFormatter={(label) => new Date(label * 1000).toLocaleString()}
                            formatter={(value: number | undefined) => [value != null ? value.toFixed(1) : "N/A", metric]}
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
        </div>
    );
}
