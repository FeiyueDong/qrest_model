"""Direct stiffness backend for qREST controllable structural models."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from qrest_model.analysis.linear_system import LinearSystem
from qrest_model.analysis.newmark import NewmarkSolver
from qrest_model.analysis.result import AnalysisMetadata, AnalysisResult, ResponseHistory, SensorResult
from qrest_model.backends.direct_linear import run_linear_direct
from qrest_model.schema import ModelConfig, load_config
from qrest_model.common.ground_motion import load_ground_motion
from qrest_model.common.response import add_absolute_floor_response
from qrest_model.exporters.backend_outputs import write_story3d_outputs
from qrest_model.models.rigid_floor import RigidFloorBuildingModel
from qrest_model.postprocess.sensor_mapping import build_sensor_result
from qrest_model.theory.story_stiffness import (
    story_stiffness_table,
)


def run(config: ModelConfig | str | Path, output_dir: str | Path | None = None) -> dict[str, Any]:
    result = run_result(config)
    if output_dir is not None:
        write_outputs(result, output_dir)
    return result.to_legacy_dict()


def run_result(config: ModelConfig | str | Path) -> AnalysisResult:
    if not isinstance(config, ModelConfig):
        config_path = Path(config)
        model_config = load_config(config_path)
        base_dir = config_path.parent
    else:
        model_config = config
        base_dir = Path(".")

    ground = load_ground_motion(model_config.ground_motion, base_dir)
    structural_model = RigidFloorBuildingModel.from_config(model_config)
    linear = run_linear_direct(
        structural_model,
        model_config.damping,
        ground["time"],
        np.column_stack([ground["ax"], ground["ay"]]),
    )
    n_steps = linear.time.size
    response = {
        "time": linear.time,
        "displacement": linear.displacement.reshape((n_steps, model_config.num_stories, 3)),
        "velocity": linear.velocity.reshape((n_steps, model_config.num_stories, 3)),
        "acceleration": linear.acceleration.reshape((n_steps, model_config.num_stories, 3)),
    }
    add_absolute_floor_response(response, ground["ax"], ground["ay"])
    sensor = build_sensor_result(
        model_config.sensors,
        response["time"],
        response["displacement"],
        response["velocity"],
        response["acceleration"],
        response["absolute_displacement"],
        response["absolute_velocity"],
        response["absolute_acceleration"],
    )
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
            backend="direct_stiffness",
            response_definition=(
                "ux/uy/rz, vx/vy/vrz, ax/ay/arz are relative response; "
                "abs_* columns include ground translation from integrated input acceleration"
            ),
            rayleigh_alpha=linear.rayleigh_alpha,
            rayleigh_beta=linear.rayleigh_beta,
            extras={
                "ground_displacement_source": response["ground_displacement_source"],
                "ground_velocity_source": response["ground_velocity_source"],
            },
        ),
        story_stiffness_rows=story_stiffness_table(model_config.stories),
    )


def solve_newmark(
    mass: np.ndarray,
    damping: np.ndarray,
    stiffness: np.ndarray,
    time: np.ndarray,
    ground_ax: np.ndarray,
    ground_ay: np.ndarray,
    num_stories: int,
    beta: float = 0.25,
    gamma: float = 0.5,
) -> dict[str, Any]:
    n_steps = time.size
    ux_influence = np.tile(np.array([1.0, 0.0, 0.0]), num_stories)
    uy_influence = np.tile(np.array([0.0, 1.0, 0.0]), num_stories)
    system = LinearSystem(
        mass=mass,
        damping=damping,
        stiffness=stiffness,
        influence=np.column_stack([ux_influence, uy_influence]),
    )
    result = NewmarkSolver(beta=beta, gamma=gamma).solve(
        system,
        time,
        np.column_stack([ground_ax, ground_ay]),
    )

    shaped = {
        "time": result.time,
        "displacement": result.displacement.reshape((n_steps, num_stories, 3)),
        "velocity": result.velocity.reshape((n_steps, num_stories, 3)),
        "acceleration": result.acceleration.reshape((n_steps, num_stories, 3)),
    }
    return shaped


def write_outputs(result: AnalysisResult | dict[str, Any], output_dir: str | Path) -> None:
    write_story3d_outputs(result, output_dir)
