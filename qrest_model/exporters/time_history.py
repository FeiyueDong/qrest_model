"""Time-history CSV exporters for generated datasets."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np

from qrest_model.schema import GroundMotionConfig
from qrest_model.common.ground_motion import load_ground_motion
from qrest_model.common.response import ground_kinematics


def write_story3d_master_time_history(output_dir: Path, result: dict[str, Any]) -> None:
    for filename, key, components in (
        ("acceleration.csv", "absolute_acceleration", ("x", "y", "rz")),
        ("velocity.csv", "absolute_velocity", ("x", "y", "rz")),
        ("displacement.csv", "absolute_displacement", ("x", "y", "rz")),
    ):
        rows = []
        values = result[key]
        for step, t in enumerate(result["time"]):
            row: dict[str, Any] = {"time": float(t)}
            for story_index in range(values.shape[1]):
                for component_index, component in enumerate(components):
                    row[f"story_{story_index + 1:02d}_{component}"] = values[step, story_index, component_index]
            rows.append(row)
        write_csv(output_dir / filename, rows)


def write_shear_master_time_history(output_dir: Path, result: dict[str, Any], config: dict[str, Any]) -> None:
    direction = str(config.get("model", {}).get("dof_per_floor", ["Ux"])[0])[-1].upper()
    direction_key = direction.lower()
    ground_motion = load_ground_motion_from_raw(config.get("ground_motion", {}))
    ground = ground_kinematics(result["time"], ground_motion["ax"], ground_motion["ay"])
    ground_index = 0 if direction == "X" else 1
    histories = (
        ("acceleration.csv", result["acceleration"] + ground["acceleration"][:, ground_index, None]),
        ("velocity.csv", result["velocity"] + ground["velocity"][:, ground_index, None]),
        ("displacement.csv", result["displacement"] + ground["displacement"][:, ground_index, None]),
    )
    for filename, values in histories:
        rows = []
        for step, t in enumerate(result["time"]):
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


def write_csv(path: str | Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        Path(path).write_text("", encoding="utf-8")
        return
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

