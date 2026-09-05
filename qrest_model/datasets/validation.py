"""Validation helpers for generated dataset backends."""

from __future__ import annotations

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
