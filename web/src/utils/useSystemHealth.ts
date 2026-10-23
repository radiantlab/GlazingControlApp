import { useCallback, useEffect, useRef, useState } from "react";
import { api, type SensorInfo, type SensorReadingResponse } from "../api";

type HealthResponse = Awaited<ReturnType<typeof api.health>>;

async function fetchDiagnostic<T>(request: (signal: AbortSignal) => Promise<T>): Promise<T> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
        return await request(controller.signal);
    } finally {
        clearTimeout(timeout);
    }
}

/** Refresh diagnostics independently so an unrelated request cannot hide health errors. */
export function useSystemHealth() {
    const [health, setHealth] = useState<HealthResponse | null>(null);
    const [healthError, setHealthError] = useState<string | null>(null);
    const [sensorError, setSensorError] = useState<string | null>(null);
    const [metricsError, setMetricsError] = useState<string | null>(null);
    const [sensors, setSensors] = useState<SensorInfo[]>([]);
    const [latestMetrics, setLatestMetrics] = useState<SensorReadingResponse[]>([]);
    const [metricsAvailable, setMetricsAvailable] = useState(false);
    const [nowSeconds, setNowSeconds] = useState(Date.now() / 1000);
    const inFlight = useRef<Promise<void> | null>(null);

    useEffect(() => {
        const interval = setInterval(() => setNowSeconds(Date.now() / 1000), 1000);
        return () => clearInterval(interval);
    }, []);

    const refreshHealth = useCallback((): Promise<void> => {
        if (inFlight.current) return inFlight.current;
        const request = Promise.all([
            fetchDiagnostic(api.health).then(value => {
                setHealth(value);
                setHealthError(null);
            }, () => {
                setHealthError("Health check unavailable. Recovery cannot be confirmed.");
            }),
            fetchDiagnostic(api.listSensors).then(value => {
                setSensors(value);
                setSensorError(null);
            }, () => {
                setSensorError("Sensor labels unavailable. Showing last known labels or device IDs.");
            }),
            fetchDiagnostic(api.getLatestMetrics).then(value => {
                setLatestMetrics(value);
                setMetricsAvailable(true);
                setMetricsError(null);
            }, () => {
                setMetricsError("Latest readings unavailable. Any displayed readings are from the last successful refresh.");
            }),
        ]).then(() => {});
        inFlight.current = request;
        return request.finally(() => { inFlight.current = null; });
    }, []);

    const healthText = healthError
        ? "health unavailable"
        : health ? `${health.status} • ${health.environment}` : "checking";

    return {
        health, healthText, healthError, sensors, latestMetrics, metricsAvailable, metricsError,
        nowSeconds, refreshHealth,
        warnings: [healthError, sensorError, metricsError].filter((error): error is string => error !== null),
    };
}
