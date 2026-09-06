"""qREST metadata exporter for generated model datasets."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from qrest_model.schema import normalize_geometry


def build_qrest_metadata(
    config: dict[str, Any],
    *,
    npts: int | None = None,
    project_name: str = "qREST_Model_Test",
    event_name: str = "MODEL_GENERATED",
    provider: str = "qREST_MODEL",
    story_height: float = 3.0,
    base_elevation: float = 0.0,
) -> dict[str, Any]:
    model = config.get("model", {})
    num_stories = int(model.get("num_stories", len(config.get("stories", [])) or 1))
    ground_motion = config.get("ground_motion", {})
    dt = float(ground_motion.get("dt", 0.02))
    if npts is None:
        npts = int(round(float(ground_motion.get("duration", 0.0)) / dt)) + 1

    geometry_raw = config.get("geometry", {})
    if not geometry_raw and (story_height != 3.0 or base_elevation != 0.0):
        geometry_raw = {
            "story_heights": [story_height for _ in range(num_stories)],
            "base_elevation": base_elevation,
        }
    geometry = normalize_geometry(geometry_raw, num_stories)
    elevations = list(geometry.elevations)
    footprint = _structural_footprint(config)
    channels = _channels(config, elevations)

    return {
        "Header": "qREST_DATA",
        "Version": [1, 0, 0],
        "Units": ["m", "s"],
        "BuildingInfo": {
            "ProjectName": project_name,
            "GeoLocation": {
                "Longitude": 0.0,
                "Latitude": 0.0,
                "NorthAngle": 0.0,
            },
            "StructuralType": "NumericalModel",
            "StructuralFootprint": footprint,
            "ElevationNum": len(elevations),
            "Elevation": elevations,
        },
        "InstrumentInfo": {
            "Provider": provider,
            "ChannelNum": len(channels),
            "Channels": channels,
        },
        "DataInfo": {
            "EventName": event_name,
            "StartTime": "1970-01-01T00:00:00.000+00:00",
            "NPTS": int(npts),
            "DT": dt,
            "Corrected": "MODEL_ABSOLUTE_RESPONSE",
        },
    }


def build_qrest_metadata_from_files(
    config_path: str | Path,
    *,
    data_path: str | Path | None = None,
    project_name: str = "qREST_Model_Test",
    event_name: str = "MODEL_GENERATED",
    provider: str = "qREST_MODEL",
    story_height: float = 3.0,
    base_elevation: float = 0.0,
) -> dict[str, Any]:
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    npts = count_csv_data_rows(data_path) if data_path is not None else None
    return build_qrest_metadata(
        config,
        npts=npts,
        project_name=project_name,
        event_name=event_name,
        provider=provider,
        story_height=story_height,
        base_elevation=base_elevation,
    )


def build_qrest_metadata_from_research_dataset(
    dataset_dir: str | Path,
    *,
    data_path: str | Path | None = None,
    project_name: str | None = None,
    event_name: str | None = None,
    provider: str = "qREST_MODEL",
) -> dict[str, Any]:
    dataset = Path(dataset_dir)
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    observation = json.loads((dataset / "metadata" / "observation.json").read_text(encoding="utf-8"))
    config = json.loads((dataset / "config.json").read_text(encoding="utf-8"))
    inferred_data_path = Path(data_path) if data_path is not None else _research_primary_observation_file(dataset, observation)
    return build_qrest_metadata(
        config,
        npts=count_csv_data_rows(inferred_data_path),
        project_name=project_name or f"qREST_Model_{manifest['name']}",
        event_name=event_name or f"MODEL_{str(manifest['name']).upper()}",
        provider=provider,
    )


def write_qrest_metadata(metadata: dict[str, Any], output_path: str | Path) -> None:
    Path(output_path).write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def count_csv_data_rows(path: str | Path | None) -> int | None:
    if path is None:
        return None
    with Path(path).open("r", newline="", encoding="utf-8") as handle:
        return sum(1 for _row in csv.DictReader(handle))


def _research_primary_observation_file(dataset: Path, observation: dict[str, Any]) -> Path:
    physical_files = observation.get("files", {}).get("physical", {})
    acceleration = physical_files.get("acceleration")
    if acceleration is None:
        raise ValueError("Research metadata generation requires physical acceleration observations.")
    return dataset / "observations" / str(acceleration)


def _channels(config: dict[str, Any], elevations: list[float]) -> list[dict[str, Any]]:
    channels = []
    observations = config.get("observations", config.get("sensors", []))
    for sensor in observations:
        direction = _physical_qrest_direction(sensor)
        if direction is None:
            continue
        story = int(sensor["story"])
        if story < 1 or story > len(elevations):
            raise ValueError(f"Sensor {sensor.get('id', len(channels) + 1)} story {story} is outside elevations.")
        index = len(channels) + 1
        channels.append(
            {
                "ChannelNo": index,
                "ChannelID": str(sensor.get("id", f"CH{index}")),
                "DeviceType": "NUMERICAL",
                "Measurand": _measurand(sensor.get("quantity", "accel")),
                "Scale": 1,
                "Azimuth": _azimuth(direction),
                "LocationXYZ": [
                    float(sensor.get("x", 0.0)),
                    float(sensor.get("y", 0.0)),
                    elevations[story - 1],
                ],
            }
        )
    return channels


def _physical_qrest_direction(sensor: dict[str, Any]) -> str | None:
    kind = _observation_kind(sensor)
    if kind == "virtual":
        return None

    dof = str(sensor.get("dof", "")).strip().upper()
    if dof and dof not in {"U", "UX", "X"}:
        raise ValueError(
            f"Observation {sensor.get('id', '<unknown>')} uses dof {dof!r}, which cannot be exported as a qREST physical channel."
        )

    direction = str(sensor.get("direction", "X")).upper()
    if direction == "RZ":
        raise ValueError(
            f"Observation {sensor.get('id', '<unknown>')} uses structural Rz, which cannot be exported as a qREST physical channel."
        )
    if direction not in {"X", "Y", "Z"}:
        raise ValueError(f"Unsupported qREST metadata sensor direction: {direction}")
    return direction


def _observation_kind(sensor: dict[str, Any]) -> str:
    raw_kind = sensor.get("kind")
    if raw_kind is not None:
        kind = str(raw_kind).lower()
        if kind not in {"physical", "virtual"}:
            raise ValueError(f"Unsupported observation kind: {raw_kind}")
        return kind

    dof = str(sensor.get("dof", "")).strip().lower()
    direction = str(sensor.get("direction", "")).upper()
    if dof in {"theta", "rotation"} or direction == "RZ":
        return "virtual"
    return "physical"


def _measurand(quantity: Any) -> str:
    quantity = str(quantity).lower()
    if quantity in {"disp", "displacement"}:
        return "Displacement"
    if quantity in {"vel", "velocity"}:
        return "Velocity"
    return "Acceleration"


def _azimuth(direction: str) -> float:
    if direction == "X":
        return 90.0
    if direction == "Y":
        return 0.0
    if direction == "Z":
        return -1.0
    raise ValueError(f"Unsupported qREST metadata sensor direction: {direction}")


def _structural_footprint(config: dict[str, Any]) -> dict[str, Any]:
    points = [
        (float(element["x"]), float(element["y"]))
        for story in _story_sources(config)
        for element in story.get("elements", [])
    ]
    if not points:
        points = [(float(sensor.get("x", 0.0)), float(sensor.get("y", 0.0))) for sensor in config.get("sensors", [])]
    if not points:
        points = [(-5.0, -3.0), (5.0, 3.0)]

    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    if min_x == max_x:
        min_x, max_x = -5.0, 5.0
    if min_y == max_y:
        min_y, max_y = -3.0, 3.0
    return {
        "Shape": "Rectangular",
        "Parameters": {
            "Length": max_x - min_x,
            "Width": max_y - min_y,
        },
        "BoundingBox": {
            "MaxX": max_x,
            "MinX": min_x,
            "MaxY": max_y,
            "MinY": min_y,
        },
    }


def _story_sources(config: dict[str, Any]) -> list[dict[str, Any]]:
    defaults = config.get("floor_defaults", {})
    stories = config.get("stories", [])
    return [defaults | story for story in stories] or [defaults]


__all__ = [
    "build_qrest_metadata",
    "build_qrest_metadata_from_files",
    "build_qrest_metadata_from_research_dataset",
    "count_csv_data_rows",
    "write_qrest_metadata",
]
