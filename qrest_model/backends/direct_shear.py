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
from qrest_model.common.provenance import direct_provenance
from qrest_model.common.response import add_absolute_shear_response
from qrest_model.schema import ShearModelConfig, load_shear_config
from qrest_model.exporters.backend_outputs import write_shear_outputs
from qrest_model.models.shear_building import ShearBuildingModel
from qrest_model.observations.shear import build_shear_sensor_result, build_shear_sensor_rows
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
            extras=direct_provenance() | {
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
    return build_shear_sensor_result(config.sensors, result, direction=config.direction)


def build_sensor_rows(config: ShearModelConfig, result: dict[str, np.ndarray]) -> list[dict[str, Any]]:
    return build_shear_sensor_rows(config.sensors, result, direction=config.direction)


def write_outputs(result: AnalysisResult | dict[str, Any], output_dir: str | Path) -> None:
    write_shear_outputs(result, output_dir)
