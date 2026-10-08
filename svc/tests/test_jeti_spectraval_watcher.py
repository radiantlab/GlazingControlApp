from __future__ import annotations

import json

from app.sensors.jeti_spectraval_watcher import JetiSpectravalFileWatcher


def _cap_row(timestamp: str, lux: float) -> str:
    return (
        f"Date and Time:; 11/18/2025; {timestamp}; ; "
        f"Ev [lx] (CIE1931 2°); {lux}; ; "
        "Spectral Values (380 nm - 1000 nm); 1; 1; 1\n"
    )


def test_watcher_picks_up_directory_created_after_start(tmp_path) -> None:
    output_dir = tmp_path / "jeti_output"
    watcher = JetiSpectravalFileWatcher(
        device_id="JETI",
        sensor_id="JETI-00",
        input_path=str(output_dir),
        label="JETI",
        svc_root=str(tmp_path),
    )

    assert list(watcher.poll()) == []

    output_dir.mkdir()
    cap_file = output_dir / "latest.cap"
    cap_file.write_text(
        (
            "Date and Time:; 11/18/2025; 08:49:54am; ; "
            "Ev [lx] (CIE1931 2°); 67.9; ; "
            "Spectral Values (380 nm - 1000 nm); 1; 1; 1\n"
        ),
        encoding="utf-8",
    )

    readings = list(watcher.poll())
    assert any(r.sensor_id == "JETI-00" and r.metric == "lux" for r in readings)


def test_watcher_resumes_cursor_and_ingests_rows_written_while_stopped(
    tmp_path,
) -> None:
    cap_file = tmp_path / "live.cap"
    cap_file.write_text(_cap_row("08:49:54am", 10.0), encoding="utf-8")
    watcher = JetiSpectravalFileWatcher(
        device_id="JETI",
        sensor_id="JETI-00",
        input_path=str(cap_file),
        label="JETI",
    )

    with cap_file.open("a", encoding="utf-8") as output:
        output.write(_cap_row("08:49:55am", 11.0))
    first = list(watcher.poll())
    assert any(r.metric == "lux" and r.value == 11.0 for r in first)
    watcher.acknowledge()

    with cap_file.open("a", encoding="utf-8") as output:
        output.write(_cap_row("08:49:56am", 12.0))

    restarted = JetiSpectravalFileWatcher(
        device_id="JETI",
        sensor_id="JETI-00",
        input_path=str(cap_file),
        label="JETI",
    )
    resumed = list(restarted.poll())
    assert any(r.metric == "lux" and r.value == 12.0 for r in resumed)


def test_watcher_persists_baseline_before_first_poll(tmp_path) -> None:
    cap_file = tmp_path / "live.cap"
    cap_file.write_text(_cap_row("08:49:54am", 10.0), encoding="utf-8")
    JetiSpectravalFileWatcher(
        device_id="JETI",
        sensor_id="JETI-00",
        input_path=str(cap_file),
        label="JETI",
    )

    with cap_file.open("a", encoding="utf-8") as output:
        output.write(_cap_row("08:49:55am", 11.0))

    restarted = JetiSpectravalFileWatcher(
        device_id="JETI",
        sensor_id="JETI-00",
        input_path=str(cap_file),
        label="JETI",
    )
    resumed = list(restarted.poll())

    assert any(r.metric == "lux" and r.value == 11.0 for r in resumed)


def test_watcher_does_not_acknowledge_an_incomplete_record(tmp_path) -> None:
    cap_file = tmp_path / "live.cap"
    watcher = JetiSpectravalFileWatcher(
        device_id="JETI",
        sensor_id="JETI-00",
        input_path=str(cap_file),
        label="JETI",
    )
    complete_row = _cap_row("08:49:54am", 13.0)
    cap_file.write_text(complete_row.rstrip("\n"), encoding="utf-8")

    assert list(watcher.poll()) == []

    with cap_file.open("a", encoding="utf-8") as output:
        output.write("\n")
    readings = list(watcher.poll())
    assert any(r.metric == "lux" and r.value == 13.0 for r in readings)


def test_watcher_accepts_uppercase_cap_extension(tmp_path) -> None:
    output_dir = tmp_path / "jeti_output"
    output_dir.mkdir()
    watcher = JetiSpectravalFileWatcher(
        device_id="JETI",
        sensor_id="JETI-00",
        input_path=str(output_dir),
        label="JETI",
    )
    cap_file = output_dir / "LATEST.CAP"
    cap_file.write_text(_cap_row("08:49:54am", 14.0), encoding="utf-8")

    readings = list(watcher.poll())
    assert any(r.metric == "lux" and r.value == 14.0 for r in readings)


def test_watcher_tails_explicit_lival_file_with_non_cap_suffix(tmp_path) -> None:
    capture_file = tmp_path / "JETI_Specbos_capture.xlsx"
    capture_file.write_text(_cap_row("08:49:54am", 15.0), encoding="utf-8")
    cursor_dir = tmp_path / "cursors"
    watcher = JetiSpectravalFileWatcher(
        device_id="JETI",
        sensor_id="SPECBOS-1",
        input_path=str(capture_file),
        input_kind="file",
        cursor_dir=str(cursor_dir),
        label="Specbos",
    )

    assert list(watcher.poll()) == []

    with capture_file.open("a", encoding="utf-8") as output:
        output.write(_cap_row("08:49:55am", 16.0))

    readings = list(watcher.poll())

    assert any(r.metric == "lux" and r.value == 16.0 for r in readings)
    assert (cursor_dir / "SPECBOS-1.glazing-cursor.json").is_file()


def test_watcher_backfills_from_beginning_in_bounded_acknowledged_batches(
    tmp_path,
) -> None:
    capture_file = tmp_path / "LiVal.xlsx"
    capture_file.write_text(
        "".join(
            [
                _cap_row("08:49:54am", 10.0),
                _cap_row("08:49:55am", 11.0),
                _cap_row("08:49:56am", 12.0),
            ]
        ),
        encoding="utf-8",
    )
    cursor_dir = tmp_path / "cursors"
    watcher = JetiSpectravalFileWatcher(
        device_id="JETI",
        sensor_id="SPECBOS-1",
        input_path=str(capture_file),
        input_kind="file",
        cursor_dir=str(cursor_dir),
        label="Specbos",
        initial_position="beginning",
        max_records_per_poll=2,
    )

    first = list(watcher.poll())
    assert [r.value for r in first if r.metric == "lux"] == [10.0, 11.0]
    watcher.acknowledge()

    second = list(watcher.poll())
    assert [r.value for r in second if r.metric == "lux"] == [12.0]
    watcher.acknowledge()
    assert list(watcher.poll()) == []

    cursor = json.loads(
        (cursor_dir / "SPECBOS-1.glazing-cursor.json").read_text(
            encoding="utf-8"
        )
    )
    assert cursor["position"] == capture_file.stat().st_size


def test_watcher_retries_unacknowledged_batch(tmp_path) -> None:
    capture_file = tmp_path / "LiVal.xlsx"
    capture_file.write_text(_cap_row("08:49:54am", 17.0), encoding="utf-8")
    watcher = JetiSpectravalFileWatcher(
        device_id="JETI",
        sensor_id="SPECBOS-1",
        input_path=str(capture_file),
        input_kind="file",
        label="Specbos",
        initial_position="beginning",
    )

    first = list(watcher.poll())
    watcher.reject()
    retried = list(watcher.poll())

    assert [r.value for r in first if r.metric == "lux"] == [17.0]
    assert [r.value for r in retried if r.metric == "lux"] == [17.0]


def test_watcher_uses_explicit_source_timezone(tmp_path) -> None:
    capture_file = tmp_path / "LiVal.xlsx"
    capture_file.write_text(_cap_row("08:49:54am", 18.0), encoding="utf-8")
    watcher = JetiSpectravalFileWatcher(
        device_id="JETI",
        sensor_id="SPECBOS-1",
        input_path=str(capture_file),
        input_kind="file",
        label="Specbos",
        initial_position="beginning",
        source_timezone="America/Los_Angeles",
    )

    lux_reading = next(r for r in watcher.poll() if r.metric == "lux")

    # 2025-11-18 08:49:54 PST.
    assert lux_reading.ts == 1763484594.0
