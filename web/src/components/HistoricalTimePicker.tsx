import { type FormEvent, useState } from "react";

export type HistoricalRange = { startTs: number; endTs: number };

interface HistoricalTimePickerProps {
    sensorLabel: string;
    range?: HistoricalRange;
    onApply: (range: HistoricalRange) => void;
    onBackToLive: () => void;
}

function inputTime(ts: number): string {
    const date = new Date(ts * 1000);
    const pad = (value: number) => String(value).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export default function HistoricalTimePicker({
    sensorLabel,
    range,
    onApply,
    onBackToLive,
}: HistoricalTimePickerProps) {
    const [start, setStart] = useState(() => (range ? inputTime(range.startTs) : ""));
    const [end, setEnd] = useState(() => (range ? inputTime(range.endTs) : ""));
    const [error, setError] = useState<string | null>(null);
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    const describeTime = (ts: number) =>
        new Date(ts * 1000).toLocaleString(undefined, { timeZoneName: "short" });

    function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const startTs = new Date(start).getTime() / 1000;
        const endTs = new Date(end).getTime() / 1000;
        // Round-trip local time to catch nonexistent times when clocks go forward.
        if (
            !Number.isFinite(startTs) ||
            !Number.isFinite(endTs) ||
            inputTime(startTs) !== start ||
            inputTime(endTs) !== end
        ) {
            setError("Choose a valid start and end time that exist in your local timezone.");
            return;
        }
        if (startTs >= endTs) {
            setError("Start must be before end.");
            return;
        }
        setError(null);
        onApply({ startTs, endTs });
    }

    return (
        <div className="historical-time-picker">
            <p className="sensor-metrics-meta">Browser-local time: {timezone}</p>
            <form
                aria-label={`Historical time range for ${sensorLabel}`}
                className="sensor-graph-controls"
                onSubmit={handleSubmit}
                noValidate
            >
                <label className="hmi-status-label">
                    Start
                    <input
                        className="sensor-graph-select"
                        type="datetime-local"
                        step={60}
                        value={start}
                        onChange={(event) => setStart(event.target.value)}
                    />
                </label>
                <label className="hmi-status-label">
                    End
                    <input
                        className="sensor-graph-select"
                        type="datetime-local"
                        step={60}
                        value={end}
                        onChange={(event) => setEnd(event.target.value)}
                    />
                </label>
                <button className="hmi-manage-btn" type="submit">
                    Show History
                </button>
                {range && (
                    <button
                        className="hmi-manage-btn"
                        type="button"
                        onClick={() => {
                            setError(null);
                            onBackToLive();
                        }}
                    >
                        Back to Live
                    </button>
                )}
                {error && <span role="alert">{error}</span>}
            </form>
            <p className="sensor-metrics-meta" role="status">
                {range
                    ? `Historical range: ${describeTime(range.startTs)} – ${describeTime(range.endTs)}`
                    : "Live mode (offline sensors show the hour before their last reading)."}
            </p>
        </div>
    );
}
