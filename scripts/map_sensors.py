from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np

MODEL_ROOT = Path(__file__).resolve().parents[1]
if str(MODEL_ROOT) not in sys.path:
    sys.path.insert(0, str(MODEL_ROOT))

from scripts.make_metadata import build_qrest_metadata, write_qrest_metadata


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
    mass_center = tuple(float(v) for v in config.get("floor_defaults", {}).get("mass_center", [0.0, 0.0]))
    for quantity in ("acceleration", "velocity", "displacement"):
        master = _read_wide_csv(master_dir / f"{quantity}.csv")
        rows = []
        for step, t in enumerate(master["time"]):
            row = {"time": t}
            for sensor in config.get("sensors", []):
                story = int(sensor["story"])
                x = float(sensor.get("x", 0.0)) - mass_center[0]
                y = float(sensor.get("y", 0.0)) - mass_center[1]
                ux = master[f"story_{story:02d}_x"][step]
                uy = master[f"story_{story:02d}_y"][step]
                rz = master[f"story_{story:02d}_rz"][step]
                direction = str(sensor.get("direction", "X")).upper()
                if direction == "X":
                    value = ux - y * rz
                elif direction == "Y":
                    value = uy + x * rz
                elif direction == "RZ":
                    value = rz
                else:
                    raise ValueError(f"Unsupported story3d sensor direction: {direction}")
                row[str(sensor["id"])] = value
            rows.append(row)
        _write_rows(output_dir / f"{quantity}.csv", rows)


def _map_shear_sensors(config: dict[str, Any], master_dir: Path, output_dir: Path) -> None:
    direction = str(config.get("model", {}).get("dof_per_floor", ["Ux"])[0])[-1].lower()
    for quantity in ("acceleration", "velocity", "displacement"):
        master = _read_wide_csv(master_dir / f"{quantity}.csv")
        rows = []
        for step, t in enumerate(master["time"]):
            row = {"time": t}
            for sensor in config.get("sensors", []):
                story = int(sensor["story"])
                row[str(sensor["id"])] = master[f"story_{story:02d}_{direction}"][step]
            rows.append(row)
        _write_rows(output_dir / f"{quantity}.csv", rows)


def _is_shear_config(config: dict[str, Any]) -> bool:
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Map model master time histories to configured sensor channels.")
    parser.add_argument("--config", required=True, help="Path to model config.json with sensors.")
    parser.add_argument("--master-dir", required=True, help="Directory containing master acceleration/velocity/displacement CSV files.")
    parser.add_argument("--output-dir", required=True, help="Directory for mapped sensor time histories.")
    parser.add_argument("--metadata-output", default=None, help="Optional qREST metadata.json output path.")
    parser.add_argument("--project-name", default="qREST_Model_Test")
    parser.add_argument("--event-name", default="MODEL_GENERATED")
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    map_sensors(
        config,
        args.master_dir,
        args.output_dir,
        metadata_output=args.metadata_output,
        project_name=args.project_name,
        event_name=args.event_name,
    )
    print(args.output_dir)


if __name__ == "__main__":
    main()
