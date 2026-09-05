"""Output helpers for model results."""

from __future__ import annotations

from pathlib import Path
import csv
import json
from typing import Any

import numpy as np


def ensure_output_dir(path: str | Path) -> Path:
    output = Path(path)
    output.mkdir(parents=True, exist_ok=True)
    return output


def write_master_csv(path: str | Path, result: dict[str, Any]) -> None:
    time = result["time"]
    abs_disp = result.get("absolute_displacement", result["displacement"])
    abs_vel = result.get("absolute_velocity", result["velocity"])
    abs_acc = result.get("absolute_acceleration", result["acceleration"])
    rows = []
    for step, t in enumerate(time):
        for story_index in range(result["displacement"].shape[1]):
            rows.append(
                {
                    "time": t,
                    "story": story_index + 1,
                    "node_or_sensor_id": f"story_{story_index + 1}",
                    "ux": result["displacement"][step, story_index, 0],
                    "uy": result["displacement"][step, story_index, 1],
                    "rz": result["displacement"][step, story_index, 2],
                    "vx": result["velocity"][step, story_index, 0],
                    "vy": result["velocity"][step, story_index, 1],
                    "vrz": result["velocity"][step, story_index, 2],
                    "ax": result["acceleration"][step, story_index, 0],
                    "ay": result["acceleration"][step, story_index, 1],
                    "arz": result["acceleration"][step, story_index, 2],
                    "abs_ux": abs_disp[step, story_index, 0],
                    "abs_uy": abs_disp[step, story_index, 1],
                    "abs_rz": abs_disp[step, story_index, 2],
                    "abs_vx": abs_vel[step, story_index, 0],
                    "abs_vy": abs_vel[step, story_index, 1],
                    "abs_vrz": abs_vel[step, story_index, 2],
                    "abs_ax": abs_acc[step, story_index, 0],
                    "abs_ay": abs_acc[step, story_index, 1],
                    "abs_arz": abs_acc[step, story_index, 2],
                }
            )
    _write_rows(path, rows)


def write_sensor_csv(path: str | Path, rows: list[dict[str, Any]]) -> None:
    _write_rows(path, rows)


def write_matrix(path: str | Path, matrix: np.ndarray) -> None:
    np.savetxt(path, matrix, delimiter=",")


def write_metadata(path: str | Path, metadata: dict[str, Any]) -> None:
    Path(path).write_text(_format_metadata(metadata), encoding="utf-8")


def _format_metadata(metadata: dict[str, Any]) -> str:
    lines = []
    for key, value in metadata.items():
        if isinstance(value, (dict, list, tuple)):
            text = json.dumps(value, ensure_ascii=False)
        else:
            text = str(value)
        lines.append(f"{key}: {text}")
    return "\n".join(lines) + "\n"


def _write_rows(path: str | Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        Path(path).write_text("", encoding="utf-8")
        return
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
