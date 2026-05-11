from __future__ import annotations

from app.sensors.t10a_client import T10AHeadConfig
from app.sensors.t10a_sim_client import T10ASimClient


def test_t10a_sim_emits_one_lux_value_per_head() -> None:
    client = T10ASimClient(
        device_id="KM-SIM",
        heads=[
            T10AHeadConfig(head_no=0, sensor_id="KM-SIM-00", label="Desk center"),
            T10AHeadConfig(head_no=1, sensor_id="KM-SIM-01", label="Desk left"),
        ],
    )

    readings = list(client.poll())
    assert len(readings) == 2

    metrics = {(r.sensor_id, r.metric) for r in readings}
    assert ("KM-SIM-00", "lux") in metrics
    assert ("KM-SIM-01", "lux") in metrics
    assert all(r.value >= 0.0 for r in readings)
