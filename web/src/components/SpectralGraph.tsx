import React, { useEffect, useState } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type SensorSpectrumResponse } from "../api";

interface SpectralGraphProps {
    sensorId: string;
    fixedTs?: number;
    height?: number;
}

export default function SpectralGraph({ sensorId, fixedTs, height = 350 }: SpectralGraphProps) {
    const [data, setData] = useState<SensorSpectrumResponse | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const loadData = async () => {
        try {
            let res: SensorSpectrumResponse;
            if (fixedTs != null) {
                res = await api.getHistoricalSpectrum(sensorId, fixedTs);
            } else {
                res = await api.getLatestSpectrum(sensorId);
            }
            setData(res);
            setError(null);
        } catch (err: any) {
            console.error("Failed to load spectral data", err);
            setError(err.message || String(err));
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        setLoading(true);
        loadData();

        if (fixedTs == null) {
            const interval = setInterval(loadData, 5000); // Poll every 5s for live data
            return () => clearInterval(interval);
        }
    }, [sensorId, fixedTs]);

    if (loading && !data) {
        return (
            <div style={{ height, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--hmi-text-muted)" }}>
                Loading spectral data...
            </div>
        );
    }

    if (error) {
        return (
            <div style={{ height, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", color: "var(--hmi-danger)", padding: 20, textAlign: "center" }}>
                <div style={{ fontWeight: "bold", marginBottom: 8 }}>Failed to load spectrum</div>
                <div style={{ fontSize: "13px", opacity: 0.8 }}>{error}</div>
            </div>
        );
    }

    if (!data || !data.values || !data.values.length) {
        return (
            <div style={{ height, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--hmi-text-muted)" }}>
                No spectral data available
            </div>
        );
    }

    const step = data.wavelength_step || 1;
    const chartData = data.values.map((val, idx) => ({
        wavelength: data.wavelength_start + idx * step,
        irradiance: val,
    }));

    const formatValue = (value: number) => {
        if (value === 0) return "0";
        if (Math.abs(value) < 0.001) {
            return value.toExponential(2);
        }
        return value.toFixed(5);
    };

    return (
        <div style={{ height, padding: "10px 10px 10px 0" }}>
            <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 90, bottom: 40 }}>
                    <defs>
                        <linearGradient id="spectralGradient" x1="0" y1="0" x2="1" y2="0">
                            <stop offset="0%" stopColor="#4b0082" />
                            <stop offset="15%" stopColor="#0000ff" />
                            <stop offset="27.5%" stopColor="#00ffff" />
                            <stop offset="47.5%" stopColor="#00ff00" />
                            <stop offset="52.5%" stopColor="#ffff00" />
                            <stop offset="60%" stopColor="#ff7f00" />
                            <stop offset="70%" stopColor="#ff0000" />
                            <stop offset="100%" stopColor="#800000" />
                        </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--hmi-border)" />
                    <XAxis
                        dataKey="wavelength"
                        stroke="var(--hmi-text-muted)"
                        tick={{ fill: 'var(--hmi-text-muted)' }}
                        label={{
                            value: 'Wavelength (nm)',
                            position: 'bottom',
                            offset: 20,
                            fill: 'var(--hmi-text-muted)',
                            style: { fontSize: '13px' }
                        }}
                    />
                    <YAxis
                        stroke="var(--hmi-text-muted)"
                        tick={{ fill: 'var(--hmi-text-muted)' }}
                        tickFormatter={formatValue}
                        label={{
                            value: 'Spectral Irradiance',
                            angle: -90,
                            position: 'left',
                            offset: 65,
                            fill: 'var(--hmi-text-muted)',
                            style: { fontSize: '13px', textAnchor: 'middle' }
                        }}
                    />
                    <Tooltip
                        contentStyle={{
                            backgroundColor: 'var(--hmi-surface)',
                            border: '1px solid var(--hmi-border)',
                            borderRadius: 4,
                            color: 'var(--hmi-text)'
                        }}
                        labelFormatter={(label) => `Wavelength: ${label} nm`}
                        formatter={(value: any) => [formatValue(Number(value)), "Irradiance"]}
                    />
                    <Area
                        type="monotone"
                        dataKey="irradiance"
                        stroke="#ffffff"
                        strokeWidth={1.5}
                        fillOpacity={0.7}
                        fill="url(#spectralGradient)"
                        animationDuration={500}
                    />
                </AreaChart>
            </ResponsiveContainer>
        </div>
    );
}
