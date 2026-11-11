import { useState, type FormEvent } from "react";

export type HistoricalRange = {
    startTs: number;
    endTs: number;
};

interface HistoricalTimePickerProps {
    isHistorical: boolean;
    onApply: (range: HistoricalRange) => void;
    onBackToLive: () => void;
}

export default function HistoricalTimePicker({
    isHistorical,
    onApply,
    onBackToLive,
}: HistoricalTimePickerProps) {
    const [start, setStart] = useState("");
    const [end, setEnd] = useState("");
    const [error, setError] = useState<string | null>(null);

    function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();

        const startTs = new Date(start).getTime() / 1000;
        const endTs = new Date(end).getTime() / 1000;

        if (!start || !end || !Number.isFinite(startTs) || !Number.isFinite(endTs)) {
            setError("Choose a valid start and end time.");
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
        <form
            aria-label="Historical time range"
            className="sensor-graph-controls"
            onSubmit={handleSubmit}
            noValidate
        >
            <label className="hmi-status-label">
                Start
                <input
                    className="sensor-graph-select"
                    type="datetime-local"
                    value={start}
                    onChange={event => setStart(event.target.value)}
                />
            </label>
            <label className="hmi-status-label">
                End
                <input
                    className="sensor-graph-select"
                    type="datetime-local"
                    value={end}
                    onChange={event => setEnd(event.target.value)}
                />
            </label>
            <button className="hmi-manage-btn" type="submit">Show History</button>
            {isHistorical && (
                <button className="hmi-manage-btn" type="button" onClick={onBackToLive}>
                    Back to Live
                </button>
            )}
            {error && <span role="alert">{error}</span>}
        </form>
    );
}
