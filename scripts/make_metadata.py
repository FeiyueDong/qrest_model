from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


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

    elevations = [
        base_elevation + story_height * story_index
        for story_index in range(num_stories)
    ]
    footprint = _structural_footprint(config)
    channels = _channels(config.get("sensors", []), elevations)

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
    npts = _count_csv_data_rows(data_path) if data_path is not None else None
    return build_qrest_metadata(
        config,
        npts=npts,
        project_name=project_name,
        event_name=event_name,
        provider=provider,
        story_height=story_height,
        base_elevation=base_elevation,
    )


def write_qrest_metadata(metadata: dict[str, Any], output_path: str | Path) -> None:
    Path(output_path).write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _channels(sensors: list[dict[str, Any]], elevations: list[float]) -> list[dict[str, Any]]:
    channels = []
    for index, sensor in enumerate(sensors, start=1):
        story = int(sensor["story"])
        if story < 1 or story > len(elevations):
            raise ValueError(f"Sensor {sensor.get('id', index)} story {story} is outside elevations.")
        direction = str(sensor.get("direction", "X")).upper()
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


def _count_csv_data_rows(path: str | Path | None) -> int | None:
    if path is None:
        return None
    with Path(path).open("r", newline="", encoding="utf-8") as handle:
        return sum(1 for _row in csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate qREST-compatible metadata JSON from a model config.")
    parser.add_argument("--config", required=True, help="Path to model config.json.")
    parser.add_argument("--data", default=None, help="Optional CSV time-history file used to infer NPTS.")
    parser.add_argument("--output", required=True, help="Output metadata.json path.")
    parser.add_argument("--project-name", default="qREST_Model_Test")
    parser.add_argument("--event-name", default="MODEL_GENERATED")
    parser.add_argument("--provider", default="qREST_MODEL")
    parser.add_argument("--story-height", type=float, default=3.0)
    parser.add_argument("--base-elevation", type=float, default=0.0)
    args = parser.parse_args()

    metadata = build_qrest_metadata_from_files(
        args.config,
        data_path=args.data,
        project_name=args.project_name,
        event_name=args.event_name,
        provider=args.provider,
        story_height=args.story_height,
        base_elevation=args.base_elevation,
    )
    write_qrest_metadata(metadata, args.output)
    print(args.output)


if __name__ == "__main__":
    main()
