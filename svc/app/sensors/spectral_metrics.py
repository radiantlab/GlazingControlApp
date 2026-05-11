from __future__ import annotations

import json
import logging
import os
import warnings
from functools import lru_cache
from typing import Sequence

import numpy as np

# colour emits a non-critical warning if matplotlib is absent; keep logs clean.
with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore",
        message='.*"Matplotlib" related API features are not available.*',
    )
    import colour  # type: ignore

logger = logging.getLogger(__name__)

_COLOUR_START_NM = 360
_VISIBLE_START_NM = 380
_VISIBLE_END_NM = 780
_VISIBLE_COUNT = _VISIBLE_END_NM - _VISIBLE_START_NM + 1

# CIE S 026 EDI conversion denominators used by luox.
_ALPHA_OPIC_EDI_DENOMINATORS = {
    "s_cone": 0.817289644883213,
    "m_cone": 1.45582633881653,
    "l_cone": 1.62890776589039,
    "rhodopic": 1.4497035760559,
    "melanopic": 1.32621318911359,
}


@lru_cache(maxsize=1)
def _load_weight_tables() -> dict[str, np.ndarray]:
    """Load and cache weight tables for 380-780 nm, 1 nm spacing."""
    tables_dir = os.path.join(os.path.dirname(__file__), "data")
    cies026_path = os.path.join(tables_dir, "cies026.json")
    ciexyz31_path = os.path.join(tables_dir, "ciexyz31.json")

    with open(cies026_path, "r", encoding="utf-8") as f:
        cies026 = json.load(f)
    with open(ciexyz31_path, "r", encoding="utf-8") as f:
        ciexyz31 = json.load(f)

    wavelengths = np.arange(_VISIBLE_START_NM, _VISIBLE_END_NM + 1)
    keys = [str(int(w)) for w in wavelengths]

    return {
        "s_cone": np.array([cies026[k]["sCone"] for k in keys], dtype=np.float64),
        "m_cone": np.array([cies026[k]["mCone"] for k in keys], dtype=np.float64),
        "l_cone": np.array([cies026[k]["lCone"] for k in keys], dtype=np.float64),
        "rhodopic": np.array([cies026[k]["rod"] for k in keys], dtype=np.float64),
        "melanopic": np.array([cies026[k]["mel"] for k in keys], dtype=np.float64),
        "X": np.array([ciexyz31[k]["X"] for k in keys], dtype=np.float64),
        "Y": np.array([ciexyz31[k]["Y"] for k in keys], dtype=np.float64),
        "Z": np.array([ciexyz31[k]["Z"] for k in keys], dtype=np.float64),
    }


def _clean_spectral_values(spectral_values: Sequence[float | str]) -> list[float]:
    cleaned: list[float] = []
    for raw in spectral_values:
        if isinstance(raw, (int, float)):
            value = float(raw)
        else:
            token = raw.strip()
            if not token:
                continue
            try:
                value = float(token)
            except ValueError:
                logger.debug("Skip non-numeric spectral token: %r", raw)
                continue
        cleaned.append(value)
    return cleaned


def _to_visible_spd_380_780(spectral_values: Sequence[float]) -> np.ndarray:
    """
    Convert a 380+nm spectrum array to a fixed 380-780, 1nm vector.

    Assumes the first element corresponds to 380 nm (JETI .cap format).
    """
    spd = np.zeros(_VISIBLE_COUNT, dtype=np.float64)
    n = min(len(spectral_values), _VISIBLE_COUNT)
    if n > 0:
        spd[:n] = np.asarray(spectral_values[:n], dtype=np.float64)
    return spd


def _safe_scalar(value: object) -> float | None:
    try:
        x = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not np.isfinite(x):
        return None
    return x


def _add_if_valid(metrics: dict[str, float], key: str, value: object) -> None:
    v = _safe_scalar(value)
    if v is not None:
        metrics[key] = v


def compute_jeti_metrics(
    lux: float | None,
    spectral_values: Sequence[float | str],
) -> dict[str, float]:
    """
    Compute luox-style metrics from one JETI spectral sample.

    Returns metric-name -> numeric value.
    """
    metrics: dict[str, float] = {}
    _add_if_valid(metrics, "lux", lux)

    cleaned = _clean_spectral_values(spectral_values)
    if not cleaned:
        return metrics

    spd_visible = _to_visible_spd_380_780(cleaned)
    weights = _load_weight_tables()

    # alpha-opic irradiance in mW/m^2
    s_cone = float(np.sum(spd_visible * weights["s_cone"]) * 1000.0)
    m_cone = float(np.sum(spd_visible * weights["m_cone"]) * 1000.0)
    l_cone = float(np.sum(spd_visible * weights["l_cone"]) * 1000.0)
    rhodopic = float(np.sum(spd_visible * weights["rhodopic"]) * 1000.0)
    melanopic = float(np.sum(spd_visible * weights["melanopic"]) * 1000.0)

    _add_if_valid(metrics, "s_cone_irradiance_mw_m2", s_cone)
    _add_if_valid(metrics, "m_cone_irradiance_mw_m2", m_cone)
    _add_if_valid(metrics, "l_cone_irradiance_mw_m2", l_cone)
    _add_if_valid(metrics, "rhodopic_irradiance_mw_m2", rhodopic)
    _add_if_valid(metrics, "melanopic_irradiance_mw_m2", melanopic)

    # alpha-opic EDI in lx
    _add_if_valid(
        metrics,
        "s_cone_edi_lx",
        s_cone / _ALPHA_OPIC_EDI_DENOMINATORS["s_cone"],
    )
    _add_if_valid(
        metrics,
        "m_cone_edi_lx",
        m_cone / _ALPHA_OPIC_EDI_DENOMINATORS["m_cone"],
    )
    _add_if_valid(
        metrics,
        "l_cone_edi_lx",
        l_cone / _ALPHA_OPIC_EDI_DENOMINATORS["l_cone"],
    )
    _add_if_valid(
        metrics,
        "rhodopic_edi_lx",
        rhodopic / _ALPHA_OPIC_EDI_DENOMINATORS["rhodopic"],
    )
    _add_if_valid(
        metrics,
        "melanopic_edi_lx",
        melanopic / _ALPHA_OPIC_EDI_DENOMINATORS["melanopic"],
    )

    # CIE 1931 xy using luox tables to align with partner's references.
    X = float(np.sum(spd_visible * weights["X"]))
    Y = float(np.sum(spd_visible * weights["Y"]))
    Z = float(np.sum(spd_visible * weights["Z"]))
    XYZ_sum = X + Y + Z
    if XYZ_sum > 0:
        x = X / XYZ_sum
        y = Y / XYZ_sum
        _add_if_valid(metrics, "cie1931_x", x)
        _add_if_valid(metrics, "cie1931_y", y)
        # Calculated illuminance (fallback/diagnostic).
        _add_if_valid(metrics, "lux_calc", Y * 683.002)

    # CCT, CRI and CIE 2017 fidelity (Rf) using colour-science.
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*Aligning.*")

            sd = colour.SpectralDistribution(
                {(_VISIBLE_START_NM + i): v for i, v in enumerate(cleaned)},
                name="JETI",
            )
            sd = sd.copy().align(colour.SpectralShape(_COLOUR_START_NM, _VISIBLE_END_NM, 1))

            XYZ_colour = colour.sd_to_XYZ(sd, method="Integration")
            xy_colour = colour.XYZ_to_xy(XYZ_colour)
            uv = colour.xy_to_UCS_uv(xy_colour)

            ohno = colour.uv_to_CCT(uv, method="Ohno 2013")
            robertson = colour.uv_to_CCT(uv, method="Robertson 1968")
            _add_if_valid(metrics, "cct_ohno_k", ohno[0])
            _add_if_valid(metrics, "duv_ohno", ohno[1])
            _add_if_valid(metrics, "cct_robertson_k", robertson[0])
            _add_if_valid(metrics, "duv_robertson", robertson[1])

            _add_if_valid(metrics, "cri_ra", colour.colour_rendering_index(sd, method="CIE 1995"))
            _add_if_valid(metrics, "cfi_rf", colour.colour_fidelity_index(sd, method="CIE 2017"))
    except Exception as e:
        logger.warning("Spectral colour metric calculation failed: %s", e)

    return metrics
