"""Official qREST model dataset case definitions."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from qrest_model.schema import (
    EULER_BEAM_2D,
    RAYLEIGH_BEAM_2D,
    RIGID_FLOOR_SHEAR_3D,
    SCHEMA_VERSION,
    SHEAR_FLEXURE_BUILDING_2D,
    SHEAR_BUILDING_1D,
    TIMOSHENKO_BEAM_2D,
)

MODEL_ROOT = Path(__file__).resolve().parents[2]
CONFIG_ROOT = MODEL_ROOT / "config"
DATASET_CONFIG_ROOT = CONFIG_ROOT / "datasets"
RESEARCH_CONFIG_ROOT = CONFIG_ROOT / "research"
SCHEMA_MODEL_TYPES = {
    RIGID_FLOOR_SHEAR_3D,
    SHEAR_BUILDING_1D,
    EULER_BEAM_2D,
    RAYLEIGH_BEAM_2D,
    TIMOSHENKO_BEAM_2D,
    SHEAR_FLEXURE_BUILDING_2D,
}
MODEL_TYPE_ALIASES = {
    "story3d": RIGID_FLOOR_SHEAR_3D,
    "shear1d": SHEAR_BUILDING_1D,
}


@dataclass(frozen=True)
class DatasetCase:
    name: str
    data_type: str
    model_type: str
    config: dict[str, Any]
    description: str
    z_channel: bool = False
    truth_policy: dict[str, Any] = field(default_factory=dict)
    observation_config: dict[str, Any] = field(default_factory=dict)
    noise_config: dict[str, Any] = field(default_factory=dict)
    export_policy: dict[str, Any] = field(default_factory=dict)
    research: dict[str, Any] = field(default_factory=dict)


def dataset_cases(config_root: str | Path = DATASET_CONFIG_ROOT) -> tuple[DatasetCase, ...]:
    root = Path(config_root)
    config_paths = sorted(root.glob("*.json"))
    if not config_paths:
        raise FileNotFoundError(f"No dataset configs found in {root}")
    return tuple(load_dataset_case(path) for path in config_paths)


def research_cases(config_root: str | Path = RESEARCH_CONFIG_ROOT) -> tuple[DatasetCase, ...]:
    return dataset_cases(config_root)


def load_dataset_case(config_path: str | Path) -> DatasetCase:
    path = Path(config_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    model_config = raw.get("model_config")
    if model_config is None:
        model_config = expand_model_config(raw, path.parent)
    else:
        model_config = resolve_model_config_paths(dict(model_config), path.parent)
    return DatasetCase(
        name=str(raw["name"]),
        data_type=str(raw["data_type"]),
        model_type=schema_model_type(str(raw["model_type"])),
        config=model_config,
        description=str(raw.get("description", "")),
        z_channel=bool(raw.get("z_channel", False)),
        truth_policy=dict(raw.get("truth_policy", {})),
        observation_config=dict(raw.get("observations", raw.get("observation_config", {}))),
        noise_config=dict(raw.get("noise", raw.get("noise_config", {}))),
        export_policy=dict(raw.get("export_policy", {})),
        research=dict(raw.get("research", {})),
    )


def expand_model_config(raw: dict[str, Any], config_dir: Path) -> dict[str, Any]:
    model_type = schema_model_type(str(raw["model_type"]))
    model = dict(raw["model"])
    model.setdefault("type", model_type)
    floor_defaults = expand_floor_defaults(dict(raw.get("floor_defaults", {})), model_type)
    stories = expand_stories(
        raw.get("stories", {"range": [1, int(model["num_stories"])]}),
        floor_defaults,
        model_type,
    )
    sensors = expand_sensor_specs(raw.get("sensors", []))
    ground_motion = resolve_ground_motion_paths(dict(raw.get("ground_motion", {})), config_dir)
    return {
        "schema_version": SCHEMA_VERSION,
        "model": model,
        "floor_defaults": floor_defaults,
        "stories": stories,
        "sensors": sensors,
        "damping": dict(raw.get("damping", {})),
        "ground_motion": ground_motion,
    }


def schema_model_type(model_type: str) -> str:
    if model_type in MODEL_TYPE_ALIASES:
        return MODEL_TYPE_ALIASES[model_type]
    if model_type in SCHEMA_MODEL_TYPES:
        return model_type
    raise ValueError(f"Unsupported dataset model_type: {model_type}")


def expand_floor_defaults(raw: dict[str, Any], model_type: str) -> dict[str, Any]:
    floor_defaults = dict(raw)
    layout = floor_defaults.pop("element_layout", None)
    if model_type == RIGID_FLOOR_SHEAR_3D and layout:
        if layout != "symmetric_four_corner":
            raise ValueError(f"Unsupported element_layout: {layout}")
        footprint = floor_defaults.pop("footprint", {"x": [-5.0, 5.0], "y": [-3.0, 3.0]})
        stiffness = floor_defaults.pop("element_stiffness", {"kx": 2.0e8, "ky": 2.0e8})
        floor_defaults["elements"] = corner_elements(
            x_min=float(footprint["x"][0]),
            x_max=float(footprint["x"][1]),
            y_min=float(footprint["y"][0]),
            y_max=float(footprint["y"][1]),
            kx=float(stiffness["kx"]),
            ky=float(stiffness["ky"]),
        )
    return floor_defaults


def expand_stories(raw: Any, floor_defaults: dict[str, Any], model_type: str) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [dict(row) for row in raw]
    if not isinstance(raw, dict) or "range" not in raw:
        raise ValueError("stories must be a list or {'range': [first, last]}")
    first, last = raw["range"]
    stories = [{"story": story} for story in range(int(first), int(last) + 1)]
    if model_type == SHEAR_BUILDING_1D and "stiffness" in floor_defaults:
        stiffness = float(floor_defaults.pop("stiffness"))
        for row in stories:
            row["stiffness"] = stiffness
    return stories


def expand_sensor_specs(specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
                sensors.extend(two_x_story_sensors(story, quantity))
        elif layout == "two_x_one_y":
            for story in stories:
                sensors.extend(two_x_story_sensors(story, quantity))
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


def two_x_story_sensors(story: int, quantity: str) -> list[dict[str, Any]]:
    return [
        {"id": f"{story:02d}f_x_yneg", "story": story, "x": 0.0, "y": -3.0, "direction": "X", "quantity": quantity},
        {"id": f"{story:02d}f_x_ypos", "story": story, "x": 0.0, "y": 3.0, "direction": "X", "quantity": quantity},
    ]


def corner_elements(x_min: float, x_max: float, y_min: float, y_max: float, kx: float, ky: float) -> list[dict[str, Any]]:
    return [
        {"id": "corner_sw", "x": x_min, "y": y_min, "kx": kx, "ky": ky},
        {"id": "corner_se", "x": x_max, "y": y_min, "kx": kx, "ky": ky},
        {"id": "corner_ne", "x": x_max, "y": y_max, "kx": kx, "ky": ky},
        {"id": "corner_nw", "x": x_min, "y": y_max, "kx": kx, "ky": ky},
    ]


def resolve_ground_motion_paths(raw: dict[str, Any], config_dir: Path) -> dict[str, Any]:
    ground_motion = dict(raw)
    for key in ("ax_file", "ay_file"):
        value = ground_motion.get(key)
        if value:
            ground_motion[key] = resolve_config_path(str(value), config_dir)
    return ground_motion


def resolve_model_config_paths(model_config: dict[str, Any], config_dir: Path) -> dict[str, Any]:
    resolved = dict(model_config)
    if "ground_motion" in resolved:
        resolved["ground_motion"] = resolve_ground_motion_paths(dict(resolved["ground_motion"]), config_dir)
    return resolved


def resolve_config_path(value: str, config_dir: Path) -> str:
    path = Path(value)
    if path.is_absolute():
        return str(path)
    model_relative = MODEL_ROOT / path
    if model_relative.exists():
        return str(model_relative)
    return str((config_dir / path).resolve())
