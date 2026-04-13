from __future__ import annotations

from app.sensors.jeti_spectraval_watcher import JetiSpectravalFileWatcher


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
