"""Rigid-floor mapping from master DOFs to sensor responses."""

from __future__ import annotations

from typing import Any

import numpy as np

from qrest_model.common.config import SensorConfig


def map_floor_motion(floor_values: np.ndarray, x: float, y: float) -> np.ndarray:
    ux = floor_values[..., 0] - y * floor_values[..., 2]
    uy = floor_values[..., 1] + x * floor_values[..., 2]
    rz = floor_values[..., 2]
    return np.stack([ux, uy, rz], axis=-1)


def build_sensor_rows(
    sensors: tuple[SensorConfig, ...],
    time: np.ndarray,
    displacement: np.ndarray,
    velocity: np.ndarray,
    acceleration: np.ndarray,
    absolute_displacement: np.ndarray | None = None,
    absolute_velocity: np.ndarray | None = None,
    absolute_acceleration: np.ndarray | None = None,
) -> list[dict[str, Any]]:
    mapped_displacement = []
    mapped_velocity = []
    mapped_acceleration = []
    mapped_absolute_displacement = []
    mapped_absolute_velocity = []
    mapped_absolute_acceleration = []
    for sensor in sensors:
        story_index = sensor.story - 1
        mapped_displacement.append(map_floor_motion(displacement[:, story_index, :], sensor.x, sensor.y))
        mapped_velocity.append(map_floor_motion(velocity[:, story_index, :], sensor.x, sensor.y))
        mapped_acceleration.append(map_floor_motion(acceleration[:, story_index, :], sensor.x, sensor.y))
        if absolute_displacement is not None:
            mapped_absolute_displacement.append(
                map_floor_motion(absolute_displacement[:, story_index, :], sensor.x, sensor.y)
            )
        if absolute_velocity is not None:
            mapped_absolute_velocity.append(
                map_floor_motion(absolute_velocity[:, story_index, :], sensor.x, sensor.y)
            )
        if absolute_acceleration is not None:
            mapped_absolute_acceleration.append(
                map_floor_motion(absolute_acceleration[:, story_index, :], sensor.x, sensor.y)
            )
    return build_sensor_rows_from_motion(
        sensors,
        time,
        tuple(mapped_displacement),
        tuple(mapped_velocity),
        tuple(mapped_acceleration),
        tuple(mapped_absolute_displacement) if mapped_absolute_displacement else None,
        tuple(mapped_absolute_velocity) if mapped_absolute_velocity else None,
        tuple(mapped_absolute_acceleration) if mapped_absolute_acceleration else None,
    )


def build_sensor_rows_from_motion(
    sensors: tuple[SensorConfig, ...],
    time: np.ndarray,
    displacement_by_sensor: tuple[np.ndarray, ...],
    velocity_by_sensor: tuple[np.ndarray, ...],
    acceleration_by_sensor: tuple[np.ndarray, ...],
    absolute_displacement_by_sensor: tuple[np.ndarray, ...] | None = None,
    absolute_velocity_by_sensor: tuple[np.ndarray, ...] | None = None,
    absolute_acceleration_by_sensor: tuple[np.ndarray, ...] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sensor_index, sensor in enumerate(sensors):
        disp = displacement_by_sensor[sensor_index]
        vel = velocity_by_sensor[sensor_index]
        acc = acceleration_by_sensor[sensor_index]
        abs_disp = _optional_motion(absolute_displacement_by_sensor, sensor_index, disp)
        abs_vel = _optional_motion(absolute_velocity_by_sensor, sensor_index, vel)
        abs_acc = _optional_motion(absolute_acceleration_by_sensor, sensor_index, acc)
        for step, t in enumerate(time):
            rows.append(
                {
                    "time": t,
                    "story": sensor.story,
                    "node_or_sensor_id": sensor.sensor_id,
                    "direction": sensor.direction,
                    "quantity": sensor.quantity,
                    "ux": disp[step, 0],
                    "uy": disp[step, 1],
                    "rz": disp[step, 2],
                    "vx": vel[step, 0],
                    "vy": vel[step, 1],
                    "vrz": vel[step, 2],
                    "ax": acc[step, 0],
                    "ay": acc[step, 1],
                    "arz": acc[step, 2],
                    "abs_ux": abs_disp[step, 0],
                    "abs_uy": abs_disp[step, 1],
                    "abs_rz": abs_disp[step, 2],
                    "abs_vx": abs_vel[step, 0],
                    "abs_vy": abs_vel[step, 1],
                    "abs_vrz": abs_vel[step, 2],
                    "abs_ax": abs_acc[step, 0],
                    "abs_ay": abs_acc[step, 1],
                    "abs_arz": abs_acc[step, 2],
                    "value": _project(sensor, abs_disp[step], abs_vel[step], abs_acc[step]),
                    "relative_value": _project(sensor, disp[step], vel[step], acc[step]),
                }
            )
    return rows


def _project(sensor: SensorConfig, disp: np.ndarray, vel: np.ndarray, acc: np.ndarray) -> float:
    vector = acc
    if sensor.quantity in {"disp", "displacement"}:
        vector = disp
    elif sensor.quantity in {"vel", "velocity"}:
        vector = vel
    index = {"X": 0, "Y": 1, "RZ": 2}[sensor.direction]
    return float(vector[index])


def _optional_motion(motions: tuple[np.ndarray, ...] | None, index: int, fallback: np.ndarray) -> np.ndarray:
    if motions is None:
        return fallback
    return motions[index]
