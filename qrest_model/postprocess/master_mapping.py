"""Map master time-history CSV files to configured sensor channels."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from qrest_model.exporters.qrest_metadata import build_qrest_metadata, write_qrest_metadata
from qrest_model.schema import normalize_config, normalize_shear_config


def map_sensors(
    config: dict[str, Any],
    master_dir: str | Path,
    output_dir: str | Path,
    *,
    metadata_output: str | Path | None = None,
    project_name: str = "qREST_Model_Test",
    event_name: str = "MODEL_GENERATED",
) -> None:
    master_dir = Path(master_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if _is_shear_config(config):
        _map_shear_sensors(config, master_dir, output_dir)
    else:
        _map_story3d_sensors(config, master_dir, output_dir)

    if metadata_output is not None:
        npts = _count_rows(output_dir / "acceleration.csv")
        metadata = build_qrest_metadata(
            config,
            npts=npts,
            project_name=project_name,
            event_name=event_name,
        )
        write_qrest_metadata(metadata, metadata_output)


def _map_story3d_sensors(config: dict[str, Any], master_dir: Path, output_dir: Path) -> None:
    model_config = normalize_config(config)
    for quantity in ("acceleration", "velocity", "displacement"):
        master = _read_wide_csv(master_dir / f"{quantity}.csv")
        rows = []
        for step, t in enumerate(master["time"]):
            row = {"time": t}
            for sensor in model_config.sensors:
                story = sensor.story
                ux = master[f"story_{story:02d}_x"][step]
                uy = master[f"story_{story:02d}_y"][step]
                rz = master[f"story_{story:02d}_rz"][step]
                if sensor.direction == "X":
                    value = ux - sensor.y * rz
                elif sensor.direction == "Y":
                    value = uy + sensor.x * rz
                elif sensor.direction == "RZ":
                    value = rz
                else:
                    raise ValueError(f"Unsupported story3d sensor direction: {sensor.direction}")
                row[sensor.sensor_id] = value
            rows.append(row)
        _write_rows(output_dir / f"{quantity}.csv", rows)


def _map_shear_sensors(config: dict[str, Any], master_dir: Path, output_dir: Path) -> None:
    model_config = normalize_shear_config(config)
    direction = model_config.direction.lower()
    for quantity in ("acceleration", "velocity", "displacement"):
        master = _read_wide_csv(master_dir / f"{quantity}.csv")
        rows = []
        for step, t in enumerate(master["time"]):
            row = {"time": t}
            for sensor in model_config.sensors:
                row[sensor.sensor_id] = master[f"story_{sensor.story:02d}_{direction}"][step]
            rows.append(row)
        _write_rows(output_dir / f"{quantity}.csv", rows)


def _is_shear_config(config: dict[str, Any]) -> bool:
    model_type = config.get("model", {}).get("type")
    if model_type is not None:
        return str(model_type) == "shear_building_1d"
    dof = tuple(config.get("model", {}).get("dof_per_floor", []))
    return dof in {("Ux",), ("Uy",)}


def _read_wide_csv(path: Path) -> dict[str, list[float]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns: dict[str, list[float]] = {name: [] for name in reader.fieldnames or []}
        for row in reader:
            for name, value in row.items():
                columns[name].append(float(value))
        return columns


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _count_rows(path: Path) -> int:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return sum(1 for _row in csv.DictReader(handle))


__all__ = ["map_sensors"]
