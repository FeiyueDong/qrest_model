"""Direct matrix backend for one-direction shear-building models."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import warnings

import numpy as np

from qrest_model.analysis.result import AnalysisMetadata, AnalysisResult, ResponseHistory, SensorResult
from qrest_model.backends.direct_linear import run_linear_direct
from qrest_model.analysis.linear_system import LinearSystem
from qrest_model.analysis.newmark import NewmarkSolver
from qrest_model.common.ground_motion import load_ground_motion
from qrest_model.common.response import add_absolute_shear_response
from qrest_model.schema import ShearModelConfig, load_shear_config
from qrest_model.exporters.backend_outputs import write_shear_outputs
from qrest_model.models.shear_building import ShearBuildingModel
from qrest_model.theory.shear_stiffness import (
    shear_story_stiffness_table,
)


def run(config: ShearModelConfig | str | Path, output_dir: str | Path | None = None) -> dict[str, Any]:
    result = run_result(config)
    if output_dir is not None:
        write_outputs(result, output_dir)
    return result.to_legacy_dict()


def run_result(config: ShearModelConfig | str | Path) -> AnalysisResult:
    if not isinstance(config, ShearModelConfig):
        config_path = Path(config)
        model_config = load_shear_config(config_path)
        base_dir = config_path.parent
    else:
        model_config = config
        base_dir = Path(".")

    ground = load_ground_motion(model_config.ground_motion, base_dir)
    ground_accel = ground["ax"] if model_config.direction == "X" else ground["ay"]
    structural_model = ShearBuildingModel.from_config(model_config)
    linear = run_linear_direct(
        structural_model,
        model_config.damping,
        ground["time"],
        ground_accel,
    )
    response = {
        "time": linear.time,
        "displacement": linear.displacement,
        "velocity": linear.velocity,
        "acceleration": linear.acceleration,
    }
    add_absolute_shear_response(response, ground["ax"], ground["ay"], model_config.direction)
    sensor = build_sensor_result(model_config, response)
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
        sensors=sensor,
        mass_matrix=linear.mass_matrix,
        stiffness_matrix=linear.stiffness_matrix,
        damping_matrix=linear.damping_matrix,
        modal=linear.modal,
        metadata=AnalysisMetadata(
            backend="direct_shear",
            response_definition=(
                "one-direction response; relative is structural response to ground, "
                "absolute includes the selected ground translation component"
            ),
            rayleigh_alpha=linear.rayleigh_alpha,
            rayleigh_beta=linear.rayleigh_beta,
            extras={
                "direction": model_config.direction,
                "ground_displacement_source": response["ground_displacement_source"],
                "ground_velocity_source": response["ground_velocity_source"],
            },
        ),
        story_stiffness_rows=shear_story_stiffness_table(model_config.stories),
    )


def solve_newmark(
    mass: np.ndarray,
    damping: np.ndarray,
    stiffness: np.ndarray,
    time: np.ndarray,
    ground_accel: np.ndarray,
    beta: float = 0.25,
    gamma: float = 0.5,
) -> dict[str, np.ndarray]:
    warnings.warn(
        "qrest_model.backends.direct_shear.solve_newmark is deprecated; "
        "use qrest_model.backends.direct_linear.run_linear_direct through run_result instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    n = mass.shape[0]
    system = LinearSystem(
        mass=mass,
        damping=damping,
        stiffness=stiffness,
        influence=np.ones(n, dtype=float),
    )
    result = NewmarkSolver(beta=beta, gamma=gamma).solve(system, time, ground_accel)
    return {
        "time": result.time,
        "displacement": result.displacement,
        "velocity": result.velocity,
        "acceleration": result.acceleration,
    }


def build_sensor_result(config: ShearModelConfig, result: dict[str, np.ndarray]) -> SensorResult:
    displacement = tuple(result["displacement"][:, sensor.story - 1] for sensor in config.sensors)
    velocity = tuple(result["velocity"][:, sensor.story - 1] for sensor in config.sensors)
    acceleration = tuple(result["acceleration"][:, sensor.story - 1] for sensor in config.sensors)
    absolute_displacement = tuple(result["absolute_displacement"][:, sensor.story - 1] for sensor in config.sensors)
    absolute_velocity = tuple(result["absolute_velocity"][:, sensor.story - 1] for sensor in config.sensors)
    absolute_acceleration = tuple(result["absolute_acceleration"][:, sensor.story - 1] for sensor in config.sensors)
    return SensorResult(
        rows=build_sensor_rows(config, result),
        displacement=displacement,
        velocity=velocity,
        acceleration=acceleration,
        absolute_displacement=absolute_displacement,
        absolute_velocity=absolute_velocity,
        absolute_acceleration=absolute_acceleration,
    )


def build_sensor_rows(config: ShearModelConfig, result: dict[str, np.ndarray]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sensor in config.sensors:
        story_index = sensor.story - 1
        for step, t in enumerate(result["time"]):
            disp = result["displacement"][step, story_index]
            vel = result["velocity"][step, story_index]
            acc = result["acceleration"][step, story_index]
            abs_disp = result["absolute_displacement"][step, story_index]
            abs_vel = result["absolute_velocity"][step, story_index]
            abs_acc = result["absolute_acceleration"][step, story_index]
            rows.append(
                {
                    "time": t,
                    "story": sensor.story,
                    "node_or_sensor_id": sensor.sensor_id,
                    "direction": config.direction,
                    "quantity": sensor.quantity,
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


def write_outputs(result: AnalysisResult | dict[str, Any], output_dir: str | Path) -> None:
    write_shear_outputs(result, output_dir)
