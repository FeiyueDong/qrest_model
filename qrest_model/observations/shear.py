"""Observation mapping for one-direction shear-building responses."""

from __future__ import annotations

from typing import Any

import numpy as np

from qrest_model.analysis.result import SensorResult
from qrest_model.observations.base import physical_channel, quantity_unit, single_dof_operator, virtual_dof_probe
from qrest_model.schema import ShearSensorConfig


def build_shear_sensor_result(
    sensors: tuple[ShearSensorConfig, ...],
    result: dict[str, np.ndarray],
    *,
    direction: str,
) -> SensorResult:
    displacement = tuple(result["displacement"][:, sensor.story - 1] for sensor in sensors)
    velocity = tuple(result["velocity"][:, sensor.story - 1] for sensor in sensors)
    acceleration = tuple(result["acceleration"][:, sensor.story - 1] for sensor in sensors)
    absolute_displacement = tuple(result["absolute_displacement"][:, sensor.story - 1] for sensor in sensors)
    absolute_velocity = tuple(result["absolute_velocity"][:, sensor.story - 1] for sensor in sensors)
    absolute_acceleration = tuple(result["absolute_acceleration"][:, sensor.story - 1] for sensor in sensors)
    return SensorResult(
        rows=build_shear_sensor_rows(sensors, result, direction=direction),
        channels=tuple(_channel(sensor, direction) for sensor in sensors),
        displacement=displacement,
        velocity=velocity,
        acceleration=acceleration,
        absolute_displacement=absolute_displacement,
        absolute_velocity=absolute_velocity,
        absolute_acceleration=absolute_acceleration,
    )


def build_shear_sensor_rows(
    sensors: tuple[ShearSensorConfig, ...],
    result: dict[str, np.ndarray],
    *,
    direction: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sensor in sensors:
        story_index = sensor.story - 1
        for step, t in enumerate(result["time"]):
            disp = result["displacement"][step, story_index]
            vel = result["velocity"][step, story_index]
            acc = result["acceleration"][step, story_index]
            abs_disp = result["absolute_displacement"][step, story_index]
            abs_vel = result["absolute_velocity"][step, story_index]
            abs_acc = result["absolute_acceleration"][step, story_index]
            unit = quantity_unit(sensor.quantity, axis="translation")
            rows.append(
                {
                    "time": t,
                    "story": sensor.story,
                    "node_or_sensor_id": sensor.sensor_id,
                    "observation_kind": sensor.kind,
                    "direction": direction,
                    "quantity": sensor.quantity,
                    "unit": unit,
                    "u": disp,
                    "v": vel,
                    "a": acc,
                    "abs_u": abs_disp,
                    "abs_v": abs_vel,
                    "abs_a": abs_acc,
                    "value": _project(sensor.quantity, abs_disp, abs_vel, abs_acc),
                    "relative_value": _project(sensor.quantity, disp, vel, acc),
                }
            )
    return rows


def _project(quantity: str, disp: float, vel: float, acc: float) -> float:
    if quantity in {"disp", "displacement"}:
        return float(disp)
    if quantity in {"vel", "velocity"}:
        return float(vel)
    return float(acc)


def _channel(sensor: ShearSensorConfig, direction: str):
    if sensor.kind == "virtual":
        return virtual_dof_probe(
            sensor.sensor_id,
            story=sensor.story,
            quantity=sensor.quantity,
            dof="U",
            source={"type": "generalized_dof", "dof": "U", "direction": direction},
            operator=single_dof_operator(
                story=sensor.story,
                quantity=sensor.quantity,
                dof="U",
                frame="relative",
            ),
        )
    return physical_channel(
        sensor.sensor_id,
        story=sensor.story,
        quantity=sensor.quantity,
        direction=direction,
        source={"type": "state_mapping", "model_dofs": ["U"]},
        operator=single_dof_operator(
            story=sensor.story,
            quantity=sensor.quantity,
            dof="U",
            frame="absolute",
        ),
    )


__all__ = ["build_shear_sensor_result", "build_shear_sensor_rows"]
