"""Direct backend for two-dimensional Euler-Bernoulli beam models."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from qrest_model.analysis.result import AnalysisMetadata, AnalysisResult, ResponseHistory, SensorResult
from qrest_model.backends.direct_linear import run_linear_direct
from qrest_model.common.ground_motion import load_ground_motion
from qrest_model.common.response import add_absolute_beam_response
from qrest_model.exporters.backend_outputs import write_beam2d_outputs
from qrest_model.models.euler_beam import EulerBeam2DModel
from qrest_model.schema import BeamSensorConfig, EulerBeamModelConfig, load_euler_config


def run(config: EulerBeamModelConfig | str | Path, output_dir: str | Path | None = None) -> dict[str, Any]:
    result = run_result(config)
    if output_dir is not None:
        write_outputs(result, output_dir)
    return result.to_legacy_dict()


def run_result(config: EulerBeamModelConfig | str | Path) -> AnalysisResult:
    if not isinstance(config, EulerBeamModelConfig):
        config_path = Path(config)
        model_config = load_euler_config(config_path)
        base_dir = config_path.parent
    else:
        model_config = config
        base_dir = Path(".")

    ground = load_ground_motion(model_config.ground_motion, base_dir)
    structural_model = EulerBeam2DModel.from_config(model_config)
    linear = run_linear_direct(
        structural_model,
        model_config.damping,
        ground["time"],
        ground["ax"],
    )
    n_steps = linear.time.size
    response = {
        "time": linear.time,
        "displacement": linear.displacement.reshape((n_steps, model_config.num_stories, 2)),
        "velocity": linear.velocity.reshape((n_steps, model_config.num_stories, 2)),
        "acceleration": linear.acceleration.reshape((n_steps, model_config.num_stories, 2)),
    }
    add_absolute_beam_response(response, ground["ax"], ground["ay"])
    return AnalysisResult(
        time=response["time"],
        relative=ResponseHistory(
            displacement=response["displacement"],
            velocity=response["velocity"],
            acceleration=response["acceleration"],
        ),
        absolute=ResponseHistory(
            displacement=response["absolute_displacement"],
            velocity=response["absolute_velocity"],
            acceleration=response["absolute_acceleration"],
        ),
        ground=ResponseHistory(
            displacement=response["ground_displacement"],
            velocity=response["ground_velocity"],
            acceleration=response["ground_acceleration"],
        ),
        sensors=build_sensor_result(model_config, response),
        mass_matrix=linear.mass_matrix,
        stiffness_matrix=linear.stiffness_matrix,
        damping_matrix=linear.damping_matrix,
        modal=linear.modal,
        metadata=AnalysisMetadata(
            backend="direct_euler",
            response_definition=(
                "u/theta, v/vtheta, a/atheta are relative Euler-Bernoulli beam response; "
                "absolute u/v/a include horizontal ground translation while theta remains bending rotation"
            ),
            rayleigh_alpha=linear.rayleigh_alpha,
            rayleigh_beta=linear.rayleigh_beta,
            extras={
                "model_type": model_config.model_type,
                "dof_per_floor": list(model_config.dof_per_floor),
                "geometry": {
                    "base_elevation": model_config.geometry.base_elevation,
                    "story_heights": list(model_config.geometry.story_heights),
                    "elevations": list(model_config.geometry.elevations),
                },
                "ground_displacement_source": response["ground_displacement_source"],
                "ground_velocity_source": response["ground_velocity_source"],
            },
        ),
        story_stiffness_rows=_section_rows(model_config),
    )


def build_sensor_result(config: EulerBeamModelConfig, result: dict[str, np.ndarray]) -> SensorResult:
    displacement = tuple(_component(result["displacement"], sensor) for sensor in config.sensors)
    velocity = tuple(_component(result["velocity"], sensor) for sensor in config.sensors)
    acceleration = tuple(_component(result["acceleration"], sensor) for sensor in config.sensors)
    absolute_displacement = tuple(_component(result["absolute_displacement"], sensor) for sensor in config.sensors)
    absolute_velocity = tuple(_component(result["absolute_velocity"], sensor) for sensor in config.sensors)
    absolute_acceleration = tuple(_component(result["absolute_acceleration"], sensor) for sensor in config.sensors)
    return SensorResult(
        rows=build_sensor_rows(config, result),
        displacement=displacement,
        velocity=velocity,
        acceleration=acceleration,
        absolute_displacement=absolute_displacement,
        absolute_velocity=absolute_velocity,
        absolute_acceleration=absolute_acceleration,
    )


def build_sensor_rows(config: EulerBeamModelConfig, result: dict[str, np.ndarray]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sensor in config.sensors:
        story_index = sensor.story - 1
        component_index = _sensor_component_index(sensor)
        for step, t in enumerate(result["time"]):
            disp = result["displacement"][step, story_index, component_index]
            vel = result["velocity"][step, story_index, component_index]
            acc = result["acceleration"][step, story_index, component_index]
            abs_disp = result["absolute_displacement"][step, story_index, component_index]
            abs_vel = result["absolute_velocity"][step, story_index, component_index]
            abs_acc = result["absolute_acceleration"][step, story_index, component_index]
            rows.append(
                {
                    "time": t,
                    "story": sensor.story,
                    "node_or_sensor_id": sensor.sensor_id,
                    "dof": sensor.dof,
                    "quantity": sensor.quantity,
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


def _section_rows(config: EulerBeamModelConfig) -> list[dict[str, Any]]:
    return [
        {
            "story": section.story,
            "height": config.geometry.story_heights[section.story - 1],
            "E": section.E,
            "A": section.A,
            "I": section.I,
            "density": section.density,
        }
        for section in config.sections
    ]


def write_outputs(result: AnalysisResult | dict[str, Any], output_dir: str | Path) -> None:
    write_beam2d_outputs(result, output_dir)


__all__ = ["build_sensor_result", "run", "run_result", "write_outputs"]
