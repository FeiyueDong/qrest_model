"""Observation mapping for two-dimensional beam-like model responses."""

from __future__ import annotations

from typing import Any

import numpy as np

from qrest_model.analysis.result import SensorResult
from qrest_model.observations.base import physical_channel, quantity_unit, single_dof_operator, virtual_dof_probe
from qrest_model.schema import BeamSensorConfig


def build_beam_sensor_result(
    sensors: tuple[BeamSensorConfig, ...],
    result: dict[str, np.ndarray],
) -> SensorResult:
    displacement = tuple(_component(result["displacement"], sensor) for sensor in sensors)
    velocity = tuple(_component(result["velocity"], sensor) for sensor in sensors)
    acceleration = tuple(_component(result["acceleration"], sensor) for sensor in sensors)
    absolute_displacement = tuple(_component(result["absolute_displacement"], sensor) for sensor in sensors)
    absolute_velocity = tuple(_component(result["absolute_velocity"], sensor) for sensor in sensors)
    absolute_acceleration = tuple(_component(result["absolute_acceleration"], sensor) for sensor in sensors)
    return SensorResult(
        rows=build_beam_sensor_rows(sensors, result),
        channels=tuple(_channel(sensor) for sensor in sensors),
        displacement=displacement,
        velocity=velocity,
        acceleration=acceleration,
        absolute_displacement=absolute_displacement,
        absolute_velocity=absolute_velocity,
        absolute_acceleration=absolute_acceleration,
    )


def build_beam_sensor_rows(
    sensors: tuple[BeamSensorConfig, ...],
    result: dict[str, np.ndarray],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sensor in sensors:
        story_index = sensor.story - 1
        component_index = _sensor_component_index(sensor)
        for step, t in enumerate(result["time"]):
            disp = result["displacement"][step, story_index, component_index]
            vel = result["velocity"][step, story_index, component_index]
            acc = result["acceleration"][step, story_index, component_index]
            abs_disp = result["absolute_displacement"][step, story_index, component_index]
            abs_vel = result["absolute_velocity"][step, story_index, component_index]
            abs_acc = result["absolute_acceleration"][step, story_index, component_index]
            unit = _sensor_unit(sensor)
            rows.append(
                {
                    "time": t,
                    "story": sensor.story,
                    "node_or_sensor_id": sensor.sensor_id,
                    "observation_kind": sensor.kind,
                    "dof": sensor.dof,
                    "quantity": sensor.quantity,
                    "unit": unit,
                    "u": result["displacement"][step, story_index, 0],
                    "theta": result["displacement"][step, story_index, 1],
                    "v": result["velocity"][step, story_index, 0],
                    "vtheta": result["velocity"][step, story_index, 1],
                    "a": result["acceleration"][step, story_index, 0],
                    "atheta": result["acceleration"][step, story_index, 1],
                    "abs_u": result["absolute_displacement"][step, story_index, 0],
                    "abs_theta": result["absolute_displacement"][step, story_index, 1],
                    "abs_v": result["absolute_velocity"][step, story_index, 0],
                    "abs_vtheta": result["absolute_velocity"][step, story_index, 1],
                    "abs_a": result["absolute_acceleration"][step, story_index, 0],
                    "abs_atheta": result["absolute_acceleration"][step, story_index, 1],
                    "value": _project(sensor.quantity, abs_disp, abs_vel, abs_acc),
                    "relative_value": _project(sensor.quantity, disp, vel, acc),
                }
            )
    return rows


def _component(values: np.ndarray, sensor: BeamSensorConfig) -> np.ndarray:
    return values[:, sensor.story - 1, _sensor_component_index(sensor)]


def _sensor_component_index(sensor: BeamSensorConfig) -> int:
    return 0 if sensor.dof == "U" else 1


def _project(quantity: str, disp: float, vel: float, acc: float) -> float:
    if quantity in {"disp", "displacement"}:
        return float(disp)
    if quantity in {"vel", "velocity"}:
        return float(vel)
    return float(acc)


def _channel(sensor: BeamSensorConfig):
    if sensor.kind == "virtual":
        return virtual_dof_probe(
            sensor.sensor_id,
            story=sensor.story,
            quantity=sensor.quantity,
            dof=sensor.dof,
            operator=single_dof_operator(
                story=sensor.story,
                quantity=sensor.quantity,
                dof=sensor.dof,
                frame="relative",
            ),
        )
    return physical_channel(
        sensor.sensor_id,
        story=sensor.story,
        quantity=sensor.quantity,
        direction="X",
        source={"type": "state_mapping", "model_dofs": [sensor.dof]},
        operator=single_dof_operator(
            story=sensor.story,
            quantity=sensor.quantity,
            dof=sensor.dof,
            frame="absolute",
        ),
    )


def _sensor_unit(sensor: BeamSensorConfig) -> str:
    axis = "rotation" if sensor.dof == "Theta" else "translation"
    return quantity_unit(sensor.quantity, axis=axis)


__all__ = ["build_beam_sensor_result", "build_beam_sensor_rows"]
