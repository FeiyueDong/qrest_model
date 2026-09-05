"""Time-history CSV exporters for generated datasets."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np

from qrest_model.analysis.result import AnalysisResult
from qrest_model.schema import GroundMotionConfig
from qrest_model.common.ground_motion import load_ground_motion


def write_story3d_master_time_history(output_dir: Path, result: AnalysisResult | dict[str, Any]) -> None:
    time = _result_time(result)
    absolute = _absolute_response(result)
    for filename, key, components in (
        ("acceleration.csv", "acceleration", ("x", "y", "rz")),
        ("velocity.csv", "velocity", ("x", "y", "rz")),
        ("displacement.csv", "displacement", ("x", "y", "rz")),
    ):
        rows = []
        values = getattr(absolute, key)
        for step, t in enumerate(time):
            row: dict[str, Any] = {"time": float(t)}
            for story_index in range(values.shape[1]):
                for component_index, component in enumerate(components):
                    row[f"story_{story_index + 1:02d}_{component}"] = values[step, story_index, component_index]
            rows.append(row)
        write_csv(output_dir / filename, rows)


def write_shear_master_time_history(
    output_dir: Path,
    result: AnalysisResult | dict[str, Any],
    config: dict[str, Any] | None = None,
) -> None:
    time = _result_time(result)
    absolute = _absolute_response(result)
    direction = _shear_direction(result, config)
    direction_key = direction.lower()
    histories = (
        ("acceleration.csv", absolute.acceleration),
        ("velocity.csv", absolute.velocity),
        ("displacement.csv", absolute.displacement),
    )
    for filename, values in histories:
        rows = []
        for step, t in enumerate(time):
            row: dict[str, Any] = {"time": float(t)}
            for story_index in range(values.shape[1]):
                row[f"story_{story_index + 1:02d}_{direction_key}"] = values[step, story_index]
            rows.append(row)
        write_csv(output_dir / filename, rows)


def load_ground_motion_from_raw(raw: dict[str, Any]) -> dict[str, np.ndarray]:
    return load_ground_motion(
        GroundMotionConfig(
            dt=float(raw.get("dt", 0.02)),
            duration=float(raw.get("duration", 0.0)),
            ax_file=raw.get("ax_file"),
            ay_file=raw.get("ay_file"),
            ax_scale=float(raw.get("ax_scale", 1.0)),
            ay_scale=float(raw.get("ay_scale", 1.0)),
            synthetic=dict(raw.get("synthetic", {})),
        )
    )


def _result_time(result: AnalysisResult | dict[str, Any]) -> np.ndarray:
    if isinstance(result, AnalysisResult):
        return result.time
    return np.asarray(result["time"], dtype=float)


def _absolute_response(result: AnalysisResult | dict[str, Any]) -> Any:
    if isinstance(result, AnalysisResult):
        if result.absolute is None:
            raise ValueError("AnalysisResult.absolute is required for time-history export.")
        return result.absolute
    return _LegacyResponse(
        displacement=np.asarray(result["absolute_displacement"], dtype=float),
        velocity=np.asarray(result["absolute_velocity"], dtype=float),
        acceleration=np.asarray(result["absolute_acceleration"], dtype=float),
    )


def _shear_direction(result: AnalysisResult | dict[str, Any], config: dict[str, Any] | None) -> str:
    if isinstance(result, AnalysisResult):
        direction = result.metadata.extras.get("direction")
        if direction is not None:
            return str(direction).upper()
    if config is not None:
        return str(config.get("model", {}).get("dof_per_floor", ["Ux"])[0])[-1].upper()
    metadata = result.get("metadata", {}) if isinstance(result, dict) else {}
    return str(metadata.get("direction", "X")).upper()


class _LegacyResponse:
    def __init__(self, displacement: np.ndarray, velocity: np.ndarray, acceleration: np.ndarray) -> None:
        self.displacement = displacement
        self.velocity = velocity
        self.acceleration = acceleration


def write_csv(path: str | Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        Path(path).write_text("", encoding="utf-8")
        return
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
