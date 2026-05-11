from __future__ import annotations

from app.sensors.eko_ms90_plus_sim_client import EkoMs90PlusSimClient


def test_eko_sim_emits_expected_metrics() -> None:
    client = EkoMs90PlusSimClient(device_id="EKO-SIM", sensor_id="EKO-SIM-00")
    readings = list(client.poll())

    assert readings
    metric_names = {r.metric for r in readings}

    expected = {
        "board_temp_c",
        "sensor_temp_c",
        "ghi_w_m2",
        "dni_w_m2",
        "dhi_w_m2",
        "latitude_deg",
        "longitude_deg",
        "sun_elevation_deg",
        "sun_azimuth_deg",
        "gps_timestamp_s",
        "gps_satellites",
    }
    assert expected.issubset(metric_names)
    assert all(r.sensor_id == "EKO-SIM-00" for r in readings)
