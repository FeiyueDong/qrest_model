from __future__ import annotations

import argparse
import csv
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any, Iterable

import numpy as np

MODEL_ROOT = Path(__file__).resolve().parents[1]
CONFIG_ROOT = MODEL_ROOT / "config"
DATASET_CONFIG_ROOT = CONFIG_ROOT / "datasets"
if str(MODEL_ROOT) not in sys.path:
    sys.path.insert(0, str(MODEL_ROOT))

from scripts.map_sensors import map_sensors
from scripts.make_algorithm_configs import write_algorithm_configs
from qrest_model.theory.sensor_mapping import map_floor_motion
from qrest_model.common.response import ground_kinematics
from qrest_model.common.io import ensure_output_dir
from qrest_model.common.ground_motion import load_ground_motion
from qrest_model.common.config import GroundMotionConfig
from qrest_model.backends.direct_stiffness import run as run_direct_stiffness
from qrest_model.backends.direct_shear import run as run_direct_shear


@dataclass(frozen=True)
class DatasetCase:
    name: str
    data_type: str
    model_type: str
    config: dict[str, Any]
    description: str
    z_channel: bool = False


def dataset_cases(config_root: str | Path = DATASET_CONFIG_ROOT) -> tuple[DatasetCase, ...]:
    root = Path(config_root)
    config_paths = sorted(root.glob("*.json"))
    if not config_paths:
        raise FileNotFoundError(f"No dataset configs found in {root}")
    return tuple(load_dataset_case(path) for path in config_paths)


def load_dataset_case(config_path: str | Path) -> DatasetCase:
    path = Path(config_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    model_config = raw.get("model_config")
    if model_config is None:
        model_config = _expand_model_config(raw, path.parent)
    return DatasetCase(
        name=str(raw["name"]),
        data_type=str(raw["data_type"]),
        model_type=str(raw["model_type"]),
        config=model_config,
        description=str(raw.get("description", "")),
        z_channel=bool(raw.get("z_channel", False)),
    )


def generate_all(
    output_root: str | Path,
    selected_names: Iterable[str] | None = None,
    config_root: str | Path = DATASET_CONFIG_ROOT,
) -> list[Path]:
    selected = set(selected_names or [])
    cases = dataset_cases(config_root)
    available = {case.name for case in cases}
    unknown = selected - available
    if unknown:
        raise ValueError(
            f"Unknown dataset case(s): {', '.join(sorted(unknown))}. "
            f"Available cases: {', '.join(sorted(available))}"
        )
    output_root = ensure_output_dir(
        output_root) if selected else _reset_output_dir(output_root)
    generated: list[Path] = []
    for case in cases:
        if selected and case.name not in selected:
            continue
        generated.append(generate_case(case, output_root / case.name))
    return generated


def generate_case(case: DatasetCase, case_dir: str | Path) -> Path:
    return _generate_official_case(case, case_dir)


def _generate_official_case(case: DatasetCase, case_dir: str | Path) -> Path:
    case_dir = _reset_output_dir(case_dir)
    config_path = case_dir / "config.json"
    config_path.write_text(json.dumps(
        case.config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if case.model_type == "shear1d":
        result = run_direct_shear(config_path)
    else:
        result = run_direct_stiffness(config_path)

    master_dir = ensure_output_dir(case_dir / "master_time_history")
    if case.model_type == "shear1d":
        _write_shear_master_time_history(master_dir, result, case.config)
    else:
        _write_story3d_master_time_history(master_dir, result)
    _write_structural_properties(
        case, case_dir / "structural_properties", result)

    time_history_dir = ensure_output_dir(case_dir / "time_history")
    map_sensors(
        case.config,
        master_dir,
        time_history_dir,
        metadata_output=case_dir / "metadata.json",
        project_name=f"qREST_Model_{case.name}",
        event_name=f"MODEL_{case.name.upper()}",
    )
    dataset_info = _dataset_info(case, result)
    (case_dir / "dataset_info.json").write_text(
        json.dumps(dataset_info, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_algorithm_configs(case_dir)
    return case_dir


def _reset_output_dir(path: str | Path) -> Path:
    output = Path(path)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    return output


def _expand_model_config(raw: dict[str, Any], config_dir: Path) -> dict[str, Any]:
    model_type = str(raw["model_type"])
    model = dict(raw["model"])
    floor_defaults = _expand_floor_defaults(
        dict(raw.get("floor_defaults", {})), model_type)
    stories = _expand_stories(
        raw.get("stories", {"range": [1, int(model["num_stories"])]}),
        floor_defaults,
        model_type,
    )
    sensors = _expand_sensor_specs(raw.get("sensors", []))
    ground_motion = _resolve_ground_motion_paths(
        dict(raw.get("ground_motion", {})), config_dir)
    config: dict[str, Any] = {
        "model": model,
        "floor_defaults": floor_defaults,
        "stories": stories,
        "sensors": sensors,
        "damping": dict(raw.get("damping", {})),
        "ground_motion": ground_motion,
    }
    return config


def _expand_floor_defaults(raw: dict[str, Any], model_type: str) -> dict[str, Any]:
    floor_defaults = dict(raw)
    layout = floor_defaults.pop("element_layout", None)
    if model_type == "story3d" and layout:
        if layout != "symmetric_four_corner":
            raise ValueError(f"Unsupported element_layout: {layout}")
        footprint = floor_defaults.pop(
            "footprint", {"x": [-5.0, 5.0], "y": [-3.0, 3.0]})
        stiffness = floor_defaults.pop(
            "element_stiffness", {"kx": 2.0e8, "ky": 2.0e8})
        floor_defaults["elements"] = _corner_elements(
            x_min=float(footprint["x"][0]),
            x_max=float(footprint["x"][1]),
            y_min=float(footprint["y"][0]),
            y_max=float(footprint["y"][1]),
            kx=float(stiffness["kx"]),
            ky=float(stiffness["ky"]),
        )
    return floor_defaults


def _expand_stories(raw: Any, floor_defaults: dict[str, Any], model_type: str) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [dict(row) for row in raw]
    if not isinstance(raw, dict) or "range" not in raw:
        raise ValueError("stories must be a list or {'range': [first, last]}")
    first, last = raw["range"]
    stories = [{"story": story} for story in range(int(first), int(last) + 1)]
    if model_type == "shear1d" and "stiffness" in floor_defaults:
        stiffness = float(floor_defaults.pop("stiffness"))
        for row in stories:
            row["stiffness"] = stiffness
    return stories


def _expand_sensor_specs(specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sensors: list[dict[str, Any]] = []
    for spec in specs:
        if "id" in spec:
            sensors.append(dict(spec))
            continue
        layout = str(spec["layout"])
        stories = [int(story) for story in spec.get("stories", [])]
        quantity = str(spec.get("quantity", "accel"))
        if layout == "single_x":
            sensors.extend(
                {"id": f"{story:02d}f_x", "story": story, "quantity": quantity}
                for story in stories
            )
        elif layout == "center_xy":
            sensors.extend(
                {"id": f"{story:02d}f_center_x", "story": story, "x": 0.0, "y": 0.0, "direction": "X", "quantity": quantity}
                for story in stories
            )
            sensors.extend(
                {"id": f"{story:02d}f_center_y", "story": story, "x": 0.0, "y": 0.0, "direction": "Y", "quantity": quantity}
                for story in stories
            )
        elif layout == "two_x":
            for story in stories:
                sensors.extend(_two_x_story_sensors(story, quantity))
        elif layout == "two_x_one_y":
            for story in stories:
                sensors.extend(_two_x_story_sensors(story, quantity))
                sensors.append(
                    {"id": f"{story:02d}f_y_xpos", "story": story, "x": 5.0, "y": 0.0, "direction": "Y", "quantity": quantity}
                )
        elif layout == "center_y":
            sensors.extend(
                {"id": f"{story:02d}f_center_y", "story": story, "x": 0.0, "y": 0.0, "direction": "Y", "quantity": quantity}
                for story in stories
            )
        else:
            raise ValueError(f"Unsupported sensor layout: {layout}")
    return sensors


def _two_x_story_sensors(story: int, quantity: str) -> list[dict[str, Any]]:
    return [
        {"id": f"{story:02d}f_x_yneg", "story": story,
            "x": 0.0, "y": -3.0, "direction": "X", "quantity": quantity},
        {"id": f"{story:02d}f_x_ypos", "story": story,
            "x": 0.0, "y": 3.0, "direction": "X", "quantity": quantity},
    ]


def _corner_elements(x_min: float, x_max: float, y_min: float, y_max: float, kx: float, ky: float) -> list[dict[str, float]]:
    return [
        {"x": x_min, "y": y_min, "kx": kx, "ky": ky},
        {"x": x_max, "y": y_min, "kx": kx, "ky": ky},
        {"x": x_max, "y": y_max, "kx": kx, "ky": ky},
        {"x": x_min, "y": y_max, "kx": kx, "ky": ky},
    ]


def _resolve_ground_motion_paths(raw: dict[str, Any], config_dir: Path) -> dict[str, Any]:
    ground_motion = dict(raw)
    for key in ("ax_file", "ay_file"):
        value = ground_motion.get(key)
        if value:
            ground_motion[key] = _resolve_config_path(str(value), config_dir)
    return ground_motion


def _resolve_config_path(value: str, config_dir: Path) -> str:
    path = Path(value)
    if path.is_absolute():
        return str(path)
    model_relative = MODEL_ROOT / path
    if model_relative.exists():
        return str(model_relative)
    return str((config_dir / path).resolve())


def _write_story3d_master_time_history(output_dir: Path, result: dict[str, Any]) -> None:
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
                    row[f"story_{story_index + 1:02d}_{component}"] = values[step,
                                                                             story_index, component_index]
            rows.append(row)
        _write_csv(output_dir / filename, rows)


def _write_shear_master_time_history(output_dir: Path, result: dict[str, Any], config: dict[str, Any]) -> None:
    direction = str(config.get("model", {}).get(
        "dof_per_floor", ["Ux"])[0])[-1].upper()
    direction_key = direction.lower()
    ground_motion = _load_ground_motion_from_raw(
        config.get("ground_motion", {}))
    ground = ground_kinematics(
        result["time"], ground_motion["ax"], ground_motion["ay"])
    ground_index = 0 if direction == "X" else 1
    histories = (
        ("acceleration.csv", result["acceleration"] +
         ground["acceleration"][:, ground_index, None]),
        ("velocity.csv", result["velocity"] +
         ground["velocity"][:, ground_index, None]),
        ("displacement.csv", result["displacement"] +
         ground["displacement"][:, ground_index, None]),
    )
    for filename, values in histories:
        rows = []
        for step, t in enumerate(result["time"]):
            row: dict[str, Any] = {"time": float(t)}
            for story_index in range(values.shape[1]):
                row[f"story_{story_index + 1:02d}_{direction_key}"] = values[step, story_index]
            rows.append(row)
        _write_csv(output_dir / filename, rows)


def _load_ground_motion_from_raw(raw: dict[str, Any]) -> dict[str, np.ndarray]:
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


def _validate_opensees_sensor_nodes(config: dict[str, Any], result: dict[str, Any]) -> dict[str, float]:
    sensors = config["sensors"]
    disp_errors = []
    vel_errors = []
    acc_errors = []
    for sensor_index, sensor in enumerate(sensors):
        story_index = int(sensor["story"]) - 1
        x = float(sensor["x"]) - \
            float(config["floor_defaults"]["mass_center"][0])
        y = float(sensor["y"]) - \
            float(config["floor_defaults"]["mass_center"][1])
        mapped_disp = map_floor_motion(
            result["displacement"][:, story_index, :], x=x, y=y)
        mapped_vel = map_floor_motion(
            result["velocity"][:, story_index, :], x=x, y=y)
        mapped_acc = map_floor_motion(
            result["acceleration"][:, story_index, :], x=x, y=y)
        disp_errors.append(
            np.max(np.abs(mapped_disp - result["sensor_displacement"][sensor_index])))
        vel_errors.append(
            np.max(np.abs(mapped_vel - result["sensor_velocity"][sensor_index])))
        acc_errors.append(
            np.max(np.abs(mapped_acc - result["sensor_acceleration"][sensor_index])))
    return {
        "sensor_node_disp_max_abs": float(max(disp_errors, default=0.0)),
        "sensor_node_vel_max_abs": float(max(vel_errors, default=0.0)),
        "sensor_node_acc_max_abs": float(max(acc_errors, default=0.0)),
    }


def _dataset_info(case: DatasetCase, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": case.name,
        "data_type": case.data_type,
        "model_type": case.model_type,
        "description": case.description,
        "time_steps": int(result["time"].size),
        "master_time_history": {
            "directory": "master_time_history",
            "format": "CSV; first column is time, each remaining column is one master mass-point component.",
        },
        "sensor_time_history": {
            "directory": "time_history",
            "format": "CSV; first column is time, each remaining column is one configured sensor channel.",
            "sensor_stories": _sensor_stories(case.config),
        },
        "structural_properties": {
            "directory": "structural_properties",
            "files": {
                "mass_matrix": "structural_properties/mass_matrix.csv",
                "stiffness_matrix": "structural_properties/stiffness_matrix.csv",
                "damping_matrix": "structural_properties/damping_matrix.csv",
                "modal_frequencies": "structural_properties/modal_frequencies.csv",
                "mode_shapes": "structural_properties/mode_shapes.csv",
                "story_stiffness": "structural_properties/story_stiffness.csv",
                "summary": "structural_properties/summary.json",
            },
        },
        "algorithm_config": {
            "directory": "config",
            "source": "generated from this dataset's metadata, structural_properties, and model footprint.",
            "oma_note": (
                "Current OMA post-processing rejects MIXED_DIRECTION datasets; this config is still generated for future algorithm research."
                if case.name == "staggered_2x_center_y"
                else "Supported by current OMA tests."
            ),
        },
        "metadata_file": "metadata.json",
    }


def _sensor_stories(config: dict[str, Any]) -> list[int]:
    return sorted({int(sensor["story"]) for sensor in config.get("sensors", [])})


def _write_csv(path: str | Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        Path(path).write_text("", encoding="utf-8")
        return
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_structural_properties(case: DatasetCase, output_dir: str | Path, result: dict[str, Any]) -> None:
    output = ensure_output_dir(output_dir)
    mass = np.asarray(result["mass_matrix"], dtype=float)
    stiffness = np.asarray(result["stiffness_matrix"], dtype=float)
    damping = np.asarray(result["damping_matrix"], dtype=float)
    dof_labels = _dof_labels(case)
    modal = _modal_properties(mass, stiffness)

    _write_matrix_csv(output / "mass_matrix.csv", mass, dof_labels, dof_labels)
    _write_matrix_csv(output / "stiffness_matrix.csv",
                      stiffness, dof_labels, dof_labels)
    _write_matrix_csv(output / "damping_matrix.csv",
                      damping, dof_labels, dof_labels)
    _write_modal_frequencies(output / "modal_frequencies.csv", modal["omega"])
    _write_mode_shapes(output / "mode_shapes.csv",
                       dof_labels, modal["mass_normalized_modes"])
    _write_csv(output / "story_stiffness.csv", result["story_stiffness_rows"])

    summary = {
        "case": case.name,
        "model_type": case.model_type,
        "dof_count": int(mass.shape[0]),
        "mode_count": int(modal["omega"].size),
        "fundamental_frequency_hz": float(modal["omega"][0] / (2.0 * np.pi)) if modal["omega"].size else None,
        "fundamental_period_s": float(2.0 * np.pi / modal["omega"][0]) if modal["omega"].size else None,
        "rayleigh_alpha": result.get("metadata", {}).get("rayleigh_alpha"),
        "rayleigh_beta": result.get("metadata", {}).get("rayleigh_beta"),
        "matrix_files_are_labelled": True,
        "mode_shape_normalization": "mass-normalized; each mode satisfies phi.T @ M @ phi = 1",
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _dof_labels(case: DatasetCase) -> list[str]:
    if case.model_type == "shear1d":
        direction = str(case.config.get("model", {}).get(
            "dof_per_floor", ["Ux"])[0])[-1].lower()
        return [f"story_{story:02d}_{direction}" for story in range(1, case.config["model"]["num_stories"] + 1)]
    return [
        f"story_{story:02d}_{component}"
        for story in range(1, case.config["model"]["num_stories"] + 1)
        for component in ("x", "y", "rz")
    ]


def _modal_properties(mass: np.ndarray, stiffness: np.ndarray) -> dict[str, np.ndarray]:
    eigenvalues, eigenvectors = np.linalg.eig(np.linalg.solve(mass, stiffness))
    eigenvalues = np.real_if_close(eigenvalues, tol=1000).real
    eigenvectors = np.real_if_close(eigenvectors, tol=1000).real
    positive = eigenvalues > 1.0e-8
    eigenvalues = eigenvalues[positive]
    eigenvectors = eigenvectors[:, positive]
    order = np.argsort(eigenvalues)
    eigenvalues = eigenvalues[order]
    eigenvectors = eigenvectors[:, order]
    omega = np.sqrt(eigenvalues)
    modes = eigenvectors.copy()
    for col in range(modes.shape[1]):
        mode = modes[:, col]
        norm = float(np.sqrt(abs(mode.T @ mass @ mode)))
        if norm > 0.0:
            mode = mode / norm
        pivot = int(np.argmax(np.abs(mode)))
        if mode[pivot] < 0.0:
            mode = -mode
        modes[:, col] = mode
    return {"omega": omega, "mass_normalized_modes": modes}


def _write_matrix_csv(path: str | Path, matrix: np.ndarray, row_labels: list[str], col_labels: list[str]) -> None:
    rows = []
    for row_index, row_label in enumerate(row_labels):
        row: dict[str, Any] = {"dof": row_label}
        for col_index, col_label in enumerate(col_labels):
            row[col_label] = matrix[row_index, col_index]
        rows.append(row)
    _write_csv(path, rows)


def _write_modal_frequencies(path: str | Path, omega: np.ndarray) -> None:
    rows = []
    for index, value in enumerate(omega, start=1):
        rows.append(
            {
                "mode": index,
                "circular_frequency_rad_s": value,
                "frequency_hz": value / (2.0 * np.pi),
                "period_s": 2.0 * np.pi / value,
            }
        )
    _write_csv(path, rows)


def _write_mode_shapes(path: str | Path, dof_labels: list[str], modes: np.ndarray) -> None:
    rows = []
    for row_index, label in enumerate(dof_labels):
        row: dict[str, Any] = {"dof": label}
        for mode_index in range(modes.shape[1]):
            row[f"mode_{mode_index + 1:02d}"] = modes[row_index, mode_index]
        rows.append(row)
    _write_csv(path, rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate qREST model test datasets.")
    parser.add_argument(
        "--output-root",
        default=str(MODEL_ROOT / "output" / "test_datasets"),
        help="Directory where case subdirectories are written.",
    )
    parser.add_argument(
        "--config-root",
        default=str(DATASET_CONFIG_ROOT),
        help="Directory containing dataset generation JSON configs.",
    )
    parser.add_argument(
        "--case",
        action="append",
        help="Generate only the selected case. May be repeated.",
    )
    args = parser.parse_args()
    generated = generate_all(args.output_root, args.case, args.config_root)
    for path in generated:
        print(path)


if __name__ == "__main__":
    main()
