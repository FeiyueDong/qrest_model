"""Generate qREST algorithm configs for model datasets."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


PYTHON_HOME = "/usr"


def write_algorithm_configs(dataset_dir: str | Path, output_dir: str | Path | None = None) -> Path:
    dataset = Path(dataset_dir)
    output = Path(output_dir) if output_dir is not None else dataset / "config"
    metadata = json.loads((dataset / "metadata.json").read_text(encoding="utf-8"))
    model_config = json.loads((dataset / "config.json").read_text(encoding="utf-8"))
    modal_rows = _read_modal_frequencies(dataset / "structural_properties" / "modal_frequencies.csv")

    dt = float(metadata["DataInfo"]["DT"])
    npts = int(metadata["DataInfo"]["NPTS"])
    nyquist = 0.5 / dt
    f0 = modal_rows[0]["frequency_hz"]
    t0 = modal_rows[0]["period_s"]
    fc_low = round(max(0.02, min(0.10, 0.12 * f0)), 6)
    fc_high = round(min(20.0, 0.80 * nyquist), 6)
    nfft = _largest_power_of_two_at_most(npts)
    init_frequencies = _initial_frequencies(modal_rows, metadata["InstrumentInfo"]["ChannelNum"])
    column_position = _column_positions(model_config)

    configs = {
        "preprocess/ButterworthFilterDenoising.json": {
            "detrend": 0,
            "fc_low": fc_low,
            "fc_high": fc_high,
            "filter_order": 2,
            "filter_type": "bandpass",
            "zero_phase": True,
        },
        "preprocess/ButterworthFilterDenoising.python.json": {
            "detrend": 0,
            "fc_low": fc_low,
            "fc_high": fc_high,
            "filter_order": 2,
            "filter_type": "bandpass",
            "zero_phase": True,
            "python_home": PYTHON_HOME,
            "python_script": "py_scripts/py_algorithm/preprocess/calculate_preprocess.py",
        },
        "preprocess/FastFourierTransform.json": {"nfft": nfft},
        "preprocess/FastFourierTransform.python.json": {
            "nfft": nfft,
            "method": "fft",
            "python_home": PYTHON_HOME,
            "python_script": "py_scripts/py_algorithm/preprocess/calculate_preprocess.py",
        },
        "preprocess/FourierDomainFilteringDenoising.json": {
            "detrend": 0,
            "fc_low": fc_low,
            "fc_high": fc_high,
            "filter_type": "bandpass",
            "window_type": "rectangular",
            "transition_band_width": 0.0,
        },
        "rr/MappingIntegral.json": {
            "fc_low": fc_low,
            "fc_high": fc_high,
            "ignore_rz": False,
            "ignore_rock": False,
            "filter_order": 2,
            "filter_type": "bandpass",
            "zero_phase": True,
            "interp_method": "spline",
        },
        "rr/MappingIntegral.python.json": {
            "fc_low": fc_low,
            "fc_high": fc_high,
            "ignore_rz": False,
            "ignore_rock": False,
            "filter_order": 2,
            "filter_type": "bandpass",
            "zero_phase": True,
            "interp_method": "spline",
            "python_home": PYTHON_HOME,
            "python_script": "py_scripts/py_algorithm/rr/calculate_rr.py",
        },
        "oma/FrequencyDomainDecomposition.json": {
            "nfft": nfft,
            "overlap": 0.5,
            "window_type": "hanning",
            "num_orders": len(init_frequencies),
            "init_frequencies": init_frequencies,
            "search_bandwidth": max(0.08, round(0.20 * f0, 6)),
            "max_singular_values": 3,
            "mac_dedup_threshold": 0.98,
            "freq_dedup_threshold": 0.03,
            "freq_cluster_bin_factor": 3,
            "freq_cluster_relative_threshold": 0.03,
            "freq_cluster_min_threshold": 0.02,
            "mac_bell_threshold": 0.5,
            "damping_min_corr": 0.02,
            "damping_max_corr": 0.95,
            "damping_min_peak_count": 3,
            "damping_peak_count": 12,
        },
        "oma/FrequencyDomainDecomposition.python.json": {
            "nfft": nfft,
            "overlap": 0.5,
            "window_type": "hanning",
            "num_orders": len(init_frequencies),
            "init_frequencies": init_frequencies,
            "search_bandwidth": max(0.08, round(0.20 * f0, 6)),
            "mac_dedup_threshold": 0.98,
            "freq_dedup_threshold": 0.03,
            "mac_bell_threshold": 0.85,
            "damping_peak_count": 4,
            "python_home": PYTHON_HOME,
            "python_script": "py_scripts/py_algorithm/oma/calculate_oma.py",
        },
        "oma/SSICOV.json": {
            "covariance_periods": 1.0,
            "methodCOV": 1,
            "svd_method": "auto",
            "Nmin": 2,
            "Nmax": 30,
            "eps_freq": 0.01,
            "eps_zeta": 0.15,
            "min_MAC": 0.97,
            "eps_cluster": 0.2,
            "min_track_length": 5,
            "match_weights": [1.0, 1.0, 0.1],
            "frequency_band": [0.2, min(5.0, round(0.9 * nyquist, 6))],
            "max_damping_ratio": 0.06,
        },
        "edp/CenterEDP.json": {},
        "edp/CenterEDP.python.json": {
            "python_home": PYTHON_HOME,
            "python_script": "py_scripts/py_algorithm/edp/calculate_edp.py",
        },
        "edp/MaxEDP.json": {"column_position": column_position},
        "edp/MaxEDP.python.json": {
            "column_position": column_position,
            "python_home": PYTHON_HOME,
            "python_script": "py_scripts/py_algorithm/edp/calculate_edp.py",
        },
        "im/IntensityMeasures.json": {
            "time_history": {},
            "peak_value": {},
            "response_spectrum": {
                "max_period": round(max(6.0, 1.8 * t0), 6),
                "period_step": 0.01,
                "damping": 0.05,
            },
            "response_spectrum_ti": {
                "period_ti": round(t0, 6),
                "damping": 0.05,
            },
            "cav": {},
            "cad": {},
            "cae": {},
            "sed": {},
            "housner_intensity": {
                "damping": 0.05,
                "housner_ti": [0.1, round(max(2.5, 1.5 * t0), 6)],
            },
            "arias_intensity": {},
            "rms_values": {},
            "significant_duration": {"duration_ti": [0.05, 0.95]},
            "duration_arias": {"duration_ti": [0.05, 0.95]},
        },
    }

    for relative_path, config in configs.items():
        path = output / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output


def write_algorithm_configs_for_root(input_root: str | Path) -> list[Path]:
    root = Path(input_root)
    cases = [root] if (root / "metadata.json").exists() else sorted(
        path for path in root.iterdir() if path.is_dir() and (path / "metadata.json").exists()
    )
    return [write_algorithm_configs(case) for case in cases]


def _read_modal_frequencies(path: Path) -> list[dict[str, float]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return [
            {
                "mode": float(row["mode"]),
                "frequency_hz": float(row["frequency_hz"]),
                "period_s": float(row["period_s"]),
            }
            for row in csv.DictReader(handle)
        ]


def _largest_power_of_two_at_most(value: int) -> int:
    power = 1
    while power * 2 <= value:
        power *= 2
    return max(power, 2)


def _initial_frequencies(modal_rows: list[dict[str, float]], channel_num: int) -> list[list[float | int]]:
    rows = modal_rows[:6]
    singular_count = max(1, min(2, channel_num))
    return [
        [round(row["frequency_hz"], 6), (index % singular_count) + 1]
        for index, row in enumerate(rows)
    ]


def _column_positions(model_config: dict[str, Any]) -> list[list[float]]:
    points = [
        (float(element["x"]), float(element["y"]))
        for element in model_config.get("floor_defaults", {}).get("elements", [])
    ]
    if not points:
        return [[-5.0, -3.0], [0.0, -3.0], [5.0, -3.0], [-5.0, 0.0], [0.0, 0.0], [5.0, 0.0], [-5.0, 3.0], [0.0, 3.0], [5.0, 3.0]]
    xs = sorted({point[0] for point in points} | {0.0})
    ys = sorted({point[1] for point in points} | {0.0})
    return [[x, y] for x in xs for y in ys]


__all__ = [
    "PYTHON_HOME",
    "write_algorithm_configs",
    "write_algorithm_configs_for_root",
]
