"""Legacy backend output exporters."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from qrest_model.analysis.result import AnalysisResult
from qrest_model.common.io import (
    ensure_output_dir,
    write_master_csv,
    write_matrix,
    write_metadata,
    write_sensor_csv,
)


def write_story3d_outputs(
    result: AnalysisResult | dict[str, Any],
    output_dir: str | Path,
    *,
    stiffness_key: str = "stiffness_matrix",
) -> None:
    legacy = _legacy_dict(result)
    output = ensure_output_dir(output_dir)
    write_master_csv(output / "master_response.csv", legacy)
    write_sensor_csv(output / "sensor_response.csv", legacy["sensor_rows"])
    write_matrix(output / "mass_matrix.txt", legacy["mass_matrix"])
    write_matrix(output / "stiffness_matrix.txt", legacy.get(stiffness_key, legacy["stiffness_matrix"]))
    write_matrix(output / "damping_matrix.txt", legacy["damping_matrix"])
    write_sensor_csv(output / "story_stiffness_theory.txt", legacy["story_stiffness_rows"])
    write_metadata(output / "metadata.txt", legacy["metadata"])


def write_shear_outputs(result: AnalysisResult | dict[str, Any], output_dir: str | Path) -> None:
    legacy = _legacy_dict(result)
    output = ensure_output_dir(output_dir)
    write_shear_master_csv(output / "master_response.csv", legacy)
    write_sensor_csv(output / "sensor_response.csv", legacy["sensor_rows"])
    write_matrix(output / "mass_matrix.txt", legacy["mass_matrix"])
    write_matrix(output / "stiffness_matrix.txt", legacy["stiffness_matrix"])
    write_matrix(output / "damping_matrix.txt", legacy["damping_matrix"])
    write_sensor_csv(output / "story_stiffness_theory.txt", legacy["story_stiffness_rows"])
    write_metadata(output / "metadata.txt", legacy["metadata"])


def write_shear_master_csv(path: str | Path, result: dict[str, np.ndarray]) -> None:
    rows: list[dict[str, Any]] = []
    for step, t in enumerate(result["time"]):
        for story_index in range(result["displacement"].shape[1]):
            rows.append(
                {
                    "time": t,
                    "story": story_index + 1,
                    "node_or_sensor_id": f"story_{story_index + 1}",
                    "u": result["displacement"][step, story_index],
                    "v": result["velocity"][step, story_index],
                    "a": result["acceleration"][step, story_index],
                }
            )
    write_sensor_csv(path, rows)


def _legacy_dict(result: AnalysisResult | dict[str, Any]) -> dict[str, Any]:
    if isinstance(result, AnalysisResult):
        return result.to_legacy_dict()
    return result
