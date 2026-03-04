from __future__ import annotations

from pathlib import Path

from app.sensors.spectral_metrics import compute_jeti_metrics


def _load_first_cap_row() -> tuple[float, list[str]]:
    cap_path = Path(__file__).resolve().parents[1] / "data" / "251118_Jeti_Spectraval_Data.cap"
    line = cap_path.read_text(encoding="latin-1").splitlines()[0]
    parts = [p.strip() for p in line.split(";")]
    lux = float(parts[5])
    spectral = parts[8:]
    return lux, spectral


def test_compute_jeti_metrics_matches_reference_row() -> None:
    lux, spectral = _load_first_cap_row()
    metrics = compute_jeti_metrics(lux=lux, spectral_values=spectral)

    # Values below are from luox-style calculations for the first sample row.
    assert metrics["lux"] == 67.9
    assert abs(metrics["cie1931_x"] - 0.3313) < 5e-4
    assert abs(metrics["cie1931_y"] - 0.3438) < 5e-4

    assert abs(metrics["s_cone_irradiance_mw_m2"] - 48.1466) < 0.1
    assert abs(metrics["m_cone_irradiance_mw_m2"] - 95.5693) < 0.1
    assert abs(metrics["l_cone_irradiance_mw_m2"] - 110.5340) < 0.1
    assert abs(metrics["rhodopic_irradiance_mw_m2"] - 90.0320) < 0.1
    assert abs(metrics["melanopic_irradiance_mw_m2"] - 80.6708) < 0.1

    assert abs(metrics["s_cone_edi_lx"] - 58.9101) < 0.1
    assert abs(metrics["m_cone_edi_lx"] - 65.6461) < 0.1
    assert abs(metrics["l_cone_edi_lx"] - 67.8577) < 0.1
    assert abs(metrics["rhodopic_edi_lx"] - 62.1037) < 0.1
    assert abs(metrics["melanopic_edi_lx"] - 60.8279) < 0.1

    assert abs(metrics["cct_ohno_k"] - 5552.2595) < 2.0
    assert abs(metrics["cct_robertson_k"] - 5550.8098) < 2.0
    assert abs(metrics["cri_ra"] - 98.25) < 0.2
    assert abs(metrics["cfi_rf"] - 97.7386) < 0.2
