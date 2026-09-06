"""Validation helpers for generated dataset backends."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np

from qrest_model.analysis.result import AnalysisResult
from qrest_model.schema import normalize_config
from qrest_model.postprocess.sensor_mapping import map_floor_motion


def validate_opensees_sensor_nodes(config: dict[str, Any], result: AnalysisResult | dict[str, Any]) -> dict[str, float]:
    model_config = normalize_config(config)
    displacement = _relative_displacement(result)
    velocity = _relative_velocity(result)
    acceleration = _relative_acceleration(result)
    sensor_displacement = _sensor_motion(result, "displacement")
    sensor_velocity = _sensor_motion(result, "velocity")
    sensor_acceleration = _sensor_motion(result, "acceleration")
    disp_errors = []
    vel_errors = []
    acc_errors = []
    for sensor_index, sensor in enumerate(model_config.sensors):
        story_index = sensor.story - 1
        mapped_disp = map_floor_motion(
            displacement[:, story_index, :], x=sensor.x, y=sensor.y
        )
        mapped_vel = map_floor_motion(
            velocity[:, story_index, :], x=sensor.x, y=sensor.y
        )
        mapped_acc = map_floor_motion(
            acceleration[:, story_index, :], x=sensor.x, y=sensor.y
        )
        disp_errors.append(
            np.max(np.abs(mapped_disp - sensor_displacement[sensor_index]))
        )
        vel_errors.append(
            np.max(np.abs(mapped_vel - sensor_velocity[sensor_index]))
        )
        acc_errors.append(
            np.max(np.abs(mapped_acc - sensor_acceleration[sensor_index]))
        )
    return {
        "sensor_node_disp_max_abs": float(max(disp_errors, default=0.0)),
        "sensor_node_vel_max_abs": float(max(vel_errors, default=0.0)),
        "sensor_node_acc_max_abs": float(max(acc_errors, default=0.0)),
    }


def _relative_displacement(result: AnalysisResult | dict[str, Any]) -> np.ndarray:
    if isinstance(result, AnalysisResult):
        return result.relative.displacement
    return np.asarray(result["displacement"], dtype=float)


def _relative_velocity(result: AnalysisResult | dict[str, Any]) -> np.ndarray:
    if isinstance(result, AnalysisResult):
        return result.relative.velocity
    return np.asarray(result["velocity"], dtype=float)


def _relative_acceleration(result: AnalysisResult | dict[str, Any]) -> np.ndarray:
    if isinstance(result, AnalysisResult):
        return result.relative.acceleration
    return np.asarray(result["acceleration"], dtype=float)


def _sensor_motion(result: AnalysisResult | dict[str, Any], key: str) -> tuple[np.ndarray, ...]:
    if isinstance(result, AnalysisResult):
        if result.sensors is None:
            raise ValueError("AnalysisResult.sensors is required for sensor-node validation.")
        value = getattr(result.sensors, key)
        if value is None:
            raise ValueError(f"AnalysisResult.sensors.{key} is required for sensor-node validation.")
        return value
    return result[f"sensor_{key}"]


def validate_research_dataset(dataset_dir: str | Path) -> dict[str, Any]:
    root = Path(dataset_dir)
    manifest = _read_json(root / "manifest.json")
    observation_metadata = _read_json(root / "metadata" / "observation.json")
    provenance = _read_json(root / "metadata" / "provenance.json")
    _validate_manifest(root, manifest, provenance)
    time = _validate_truth(root)
    _validate_derived(root, manifest, time)
    _validate_observations(root, observation_metadata, time)
    _validate_content_summary(manifest, observation_metadata, time)
    return {
        "name": manifest["name"],
        "model_type": manifest["model_type"],
        "time_steps": int(time.size),
        "physical_channel_count": int(observation_metadata["physical_channel_count"]),
        "virtual_channel_count": int(observation_metadata["virtual_channel_count"]),
    }


def validate_research_dataset_collection(output_root: str | Path) -> dict[str, Any]:
    root = Path(output_root)
    collection = _read_json(root / "manifest.json")
    if collection.get("index_type") != "research_dataset_collection":
        raise ValueError("Research dataset collection manifest has invalid index_type.")
    datasets = collection.get("datasets")
    if not isinstance(datasets, list):
        raise ValueError("Research dataset collection manifest datasets must be a list.")
    if len(datasets) != int(collection.get("dataset_count", -1)):
        raise ValueError("Research dataset collection dataset_count does not match datasets.")
    names: list[str] = []
    for entry in datasets:
        if not isinstance(entry, dict):
            raise ValueError("Research dataset collection entry must be an object.")
        path = root / str(entry.get("path", ""))
        summary = validate_research_dataset(path)
        manifest = _read_json(path / "manifest.json")
        observation = _read_json(path / "metadata" / "observation.json")
        derived = _read_json(path / "metadata" / "derived.json")
        _validate_collection_entry(entry, manifest, observation, derived, summary)
        names.append(str(entry["name"]))
    if names != sorted(names):
        raise ValueError("Research dataset collection entries must be sorted by name.")
    return {
        "index_type": collection["index_type"],
        "dataset_count": len(datasets),
        "datasets": names,
    }


def _validate_manifest(root: Path, manifest: dict[str, Any], provenance: dict[str, Any]) -> None:
    for key in ("name", "dataset_type", "model_type", "backend", "config_hash_sha256"):
        if key not in manifest:
            raise ValueError(f"Research dataset manifest is missing {key}.")
    if manifest["dataset_type"] != "research":
        raise ValueError("Research dataset manifest dataset_type must be 'research'.")
    if manifest["config_hash_sha256"] != provenance.get("config_hash_sha256"):
        raise ValueError("Research dataset config hash differs between manifest and provenance.")
    for required in (
        root / "config.json",
        root / "truth" / "response.npz",
        root / "truth" / "matrices.npz",
        root / "truth" / "modal.npz",
        root / "truth" / "structural_properties.json",
        root / "derived" / "structural.npz",
        root / "metadata" / "derived.json",
        root / "metadata" / "observation.json",
        root / "metadata" / "provenance.json",
    ):
        if not required.exists():
            raise FileNotFoundError(f"Research dataset is missing required file: {required}")


def _validate_truth(root: Path) -> np.ndarray:
    with np.load(root / "truth" / "response.npz") as response:
        time = np.asarray(response["time"], dtype=float)
        if time.ndim != 1 or time.size == 0:
            raise ValueError("Research truth time must be a non-empty one-dimensional array.")
        for key in ("relative_displacement", "relative_velocity", "relative_acceleration"):
            values = np.asarray(response[key], dtype=float)
            if values.shape[0] != time.size:
                raise ValueError(f"Research truth {key} does not match time length.")
            if not np.all(np.isfinite(values)):
                raise ValueError(f"Research truth {key} must be finite.")
    with np.load(root / "truth" / "matrices.npz") as matrices:
        mass = np.asarray(matrices["mass_matrix"], dtype=float)
        stiffness = np.asarray(matrices["stiffness_matrix"], dtype=float)
        damping = np.asarray(matrices["damping_matrix"], dtype=float)
        for name, matrix in (("mass_matrix", mass), ("stiffness_matrix", stiffness), ("damping_matrix", damping)):
            if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
                raise ValueError(f"Research truth {name} must be square.")
            if not np.all(np.isfinite(matrix)):
                raise ValueError(f"Research truth {name} must be finite.")
    return time


def _validate_derived(root: Path, manifest: dict[str, Any], time: np.ndarray) -> None:
    metadata_path = root / str(manifest.get("metadata", {}).get("derived", "metadata/derived.json"))
    metadata = _read_json(metadata_path)
    quantities = metadata.get("quantities", [])
    if len(quantities) != int(metadata.get("quantity_count", 0)):
        raise ValueError("Derived metadata quantity_count does not match quantities.")
    npz_path = root / "derived" / str(metadata.get("files", {}).get("structural", "structural.npz"))
    with np.load(npz_path) as arrays:
        derived_time = np.asarray(arrays["time"], dtype=float)
        if not np.allclose(derived_time, time, rtol=0.0, atol=1.0e-12):
            raise ValueError("Derived structural time does not match truth time.")
        for quantity in quantities:
            quantity_id = str(quantity.get("id"))
            if quantity_id not in arrays:
                raise ValueError(f"Derived structural file is missing {quantity_id}.")
            values = np.asarray(arrays[quantity_id], dtype=float)
            if list(values.shape) != quantity.get("shape"):
                raise ValueError(f"Derived quantity {quantity_id} shape does not match metadata.")
            if values.shape[0] != time.size:
                raise ValueError(f"Derived quantity {quantity_id} does not match truth time length.")
            if not np.all(np.isfinite(values)):
                raise ValueError(f"Derived quantity {quantity_id} must be finite.")
            if not quantity.get("unit"):
                raise ValueError(f"Derived quantity {quantity_id} is missing unit.")


def _validate_observations(root: Path, metadata: dict[str, Any], time: np.ndarray) -> None:
    channels = metadata.get("channels", [])
    if len(channels) != int(metadata.get("channel_count", 0)):
        raise ValueError("Observation metadata channel_count does not match channels.")
    physical = [channel for channel in channels if channel.get("kind") == "physical"]
    virtual = [channel for channel in channels if channel.get("kind") == "virtual"]
    if len(physical) != int(metadata.get("physical_channel_count", 0)):
        raise ValueError("Observation metadata physical_channel_count does not match channels.")
    if len(virtual) != int(metadata.get("virtual_channel_count", 0)):
        raise ValueError("Observation metadata virtual_channel_count does not match channels.")
    for channel in physical:
        if channel.get("dof") is not None:
            raise ValueError(f"Physical observation {channel.get('id')} must not expose generalized dof.")
        if channel.get("direction") not in {"X", "Y", "Z"}:
            raise ValueError(f"Physical observation {channel.get('id')} must define X/Y/Z direction.")
    for channel in channels:
        if not channel.get("unit"):
            raise ValueError(f"Observation {channel.get('id')} is missing unit.")
        _validate_observation_operator(channel)
    for kind, quantity_files in metadata.get("files", {}).items():
        for quantity, relative_path in quantity_files.items():
            _validate_observation_csv(root / "observations" / relative_path, time, channels, kind, quantity)


def _validate_observation_operator(channel: dict[str, Any]) -> None:
    operator = channel.get("operator")
    if not isinstance(operator, dict):
        raise ValueError(f"Observation {channel.get('id')} is missing observation operator.")
    if operator.get("form") != "linear_combination":
        raise ValueError(f"Observation {channel.get('id')} has unsupported observation operator form.")
    terms = operator.get("terms")
    if not isinstance(terms, list) or not terms:
        raise ValueError(f"Observation {channel.get('id')} observation operator must define terms.")
    for term in terms:
        if not isinstance(term, dict):
            raise ValueError(f"Observation {channel.get('id')} observation operator term must be an object.")
        if term.get("frame") not in {"relative", "absolute", "ground"}:
            raise ValueError(f"Observation {channel.get('id')} observation operator term has invalid frame.")
        if _canonical_quantity(str(term.get("quantity"))) != _canonical_quantity(str(channel.get("quantity"))):
            raise ValueError(f"Observation {channel.get('id')} observation operator quantity does not match channel.")
        if int(term.get("story", -1)) < 0:
            raise ValueError(f"Observation {channel.get('id')} observation operator term has invalid story.")
        if not term.get("dof"):
            raise ValueError(f"Observation {channel.get('id')} observation operator term is missing dof.")
        coefficient = float(term.get("coefficient"))
        if not np.isfinite(coefficient):
            raise ValueError(f"Observation {channel.get('id')} observation operator term coefficient must be finite.")


def _validate_observation_csv(
    path: Path,
    time: np.ndarray,
    channels: list[dict[str, Any]],
    kind: str,
    quantity: str,
) -> None:
    expected_ids = [
        str(channel["id"])
        for channel in channels
        if channel.get("kind") == kind and _canonical_quantity(str(channel.get("quantity"))) == quantity
    ]
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["time", *expected_ids]:
            raise ValueError(f"{path} header does not match observation metadata.")
        rows = list(reader)
    if len(rows) != time.size:
        raise ValueError(f"{path} row count does not match truth time length.")
    for index, row in enumerate(rows):
        if not np.isclose(float(row["time"]), float(time[index]), rtol=0.0, atol=1.0e-12):
            raise ValueError(f"{path} time column does not match truth time.")
        for channel_id in expected_ids:
            float(row[channel_id])


def _validate_content_summary(
    manifest: dict[str, Any],
    observation_metadata: dict[str, Any],
    time: np.ndarray,
) -> None:
    summary = manifest.get("content_summary")
    if not isinstance(summary, dict):
        raise ValueError("Research dataset manifest is missing content_summary.")
    if int(summary.get("time_steps", -1)) != time.size:
        raise ValueError("Research dataset content_summary time_steps does not match truth.")
    if int(summary.get("physical_channel_count", -1)) != int(observation_metadata["physical_channel_count"]):
        raise ValueError("Research dataset content_summary physical_channel_count does not match observations.")
    if int(summary.get("virtual_channel_count", -1)) != int(observation_metadata["virtual_channel_count"]):
        raise ValueError("Research dataset content_summary virtual_channel_count does not match observations.")


def _validate_collection_entry(
    entry: dict[str, Any],
    manifest: dict[str, Any],
    observation: dict[str, Any],
    derived: dict[str, Any],
    summary: dict[str, Any],
) -> None:
    for key in ("name", "path", "dataset_type", "model_type", "backend", "config_hash_sha256"):
        if key not in entry:
            raise ValueError(f"Research dataset collection entry is missing {key}.")
    for key in ("name", "dataset_type", "model_type", "backend", "config_hash_sha256"):
        if entry[key] != manifest[key]:
            raise ValueError(f"Research dataset collection entry {entry['name']} has inconsistent {key}.")
    content_summary = entry.get("content_summary")
    if content_summary != manifest.get("content_summary", {}):
        raise ValueError(f"Research dataset collection entry {entry['name']} has inconsistent content_summary.")
    observations = entry.get("observations", {})
    for key in ("channel_count", "physical_channel_count", "virtual_channel_count"):
        if int(observations.get(key, -1)) != int(observation[key]):
            raise ValueError(f"Research dataset collection entry {entry['name']} has inconsistent observations.")
    derived_summary = entry.get("derived", {})
    quantity_ids = [
        str(quantity["id"])
        for quantity in derived.get("quantities", [])
    ]
    if int(derived_summary.get("quantity_count", -1)) != len(quantity_ids):
        raise ValueError(f"Research dataset collection entry {entry['name']} has inconsistent derived count.")
    if derived_summary.get("quantity_ids") != quantity_ids:
        raise ValueError(f"Research dataset collection entry {entry['name']} has inconsistent derived quantities.")
    truth = entry.get("truth", {})
    if int(truth.get("time_steps", -1)) != int(summary["time_steps"]):
        raise ValueError(f"Research dataset collection entry {entry['name']} has inconsistent truth time_steps.")


def _canonical_quantity(quantity: str) -> str:
    normalized = quantity.lower()
    if normalized in {"disp", "displacement"}:
        return "displacement"
    if normalized in {"vel", "velocity"}:
        return "velocity"
    if normalized in {"accel", "acceleration"}:
        return "acceleration"
    raise ValueError(f"Unsupported observation quantity: {quantity}")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


__all__ = [
    "validate_opensees_sensor_nodes",
    "validate_research_dataset",
    "validate_research_dataset_collection",
]
