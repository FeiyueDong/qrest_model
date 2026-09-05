"""Validation helpers for generated dataset backends."""

from __future__ import annotations

from typing import Any

import numpy as np

from qrest_model.schema import normalize_config
from qrest_model.postprocess.sensor_mapping import map_floor_motion


def validate_opensees_sensor_nodes(config: dict[str, Any], result: dict[str, Any]) -> dict[str, float]:
    model_config = normalize_config(config)
    disp_errors = []
    vel_errors = []
    acc_errors = []
    for sensor_index, sensor in enumerate(model_config.sensors):
        story_index = sensor.story - 1
        mapped_disp = map_floor_motion(
            result["displacement"][:, story_index, :], x=sensor.x, y=sensor.y
        )
        mapped_vel = map_floor_motion(
            result["velocity"][:, story_index, :], x=sensor.x, y=sensor.y
        )
        mapped_acc = map_floor_motion(
            result["acceleration"][:, story_index, :], x=sensor.x, y=sensor.y
        )
        disp_errors.append(
            np.max(np.abs(mapped_disp - result["sensor_displacement"][sensor_index]))
        )
        vel_errors.append(
            np.max(np.abs(mapped_vel - result["sensor_velocity"][sensor_index]))
        )
        acc_errors.append(
            np.max(np.abs(mapped_acc - result["sensor_acceleration"][sensor_index]))
        )
    return {
        "sensor_node_disp_max_abs": float(max(disp_errors, default=0.0)),
        "sensor_node_vel_max_abs": float(max(vel_errors, default=0.0)),
        "sensor_node_acc_max_abs": float(max(acc_errors, default=0.0)),
    }

