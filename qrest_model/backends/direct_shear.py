"""Direct matrix backend for one-direction shear-building models."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from qrest_model.analysis.linear_system import LinearSystem
from qrest_model.analysis.newmark import NewmarkSolver
from qrest_model.analysis.result import AnalysisMetadata, AnalysisResult, ResponseHistory, SensorResult
from qrest_model.common.damping import rayleigh_coefficients, rayleigh_matrix
from qrest_model.common.ground_motion import load_ground_motion
from qrest_model.schema import ShearModelConfig, load_shear_config
from qrest_model.exporters.backend_outputs import write_shear_master_csv, write_shear_outputs
from qrest_model.models.shear_building import ShearBuildingModel
from qrest_model.theory.shear_stiffness import (
    shear_story_stiffness_table,
)


def run(config: ShearModelConfig | str | Path, output_dir: str | Path | None = None) -> dict[str, Any]:
    result = run_result(config)
    legacy = result.to_legacy_dict()
    if output_dir is not None:
        write_outputs(legacy, output_dir)
    return legacy


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
    mass = structural_model.mass_matrix()
    stiffness = structural_model.stiffness_matrix()
    damping = rayleigh_matrix(mass, stiffness, model_config.damping)
    alpha, beta = rayleigh_coefficients(mass, stiffness, model_config.damping)

    response = solve_newmark(
        mass=mass,
        damping=damping,
        stiffness=stiffness,
        time=ground["time"],
        ground_accel=ground_accel,
    )
    return AnalysisResult(
        time=response["time"],
        relative=ResponseHistory(
            displacement=response["displacement"],
            velocity=response["velocity"],
            acceleration=response["acceleration"],
        ),
        sensors=SensorResult(rows=build_sensor_rows(model_config, response)),
        mass_matrix=mass,
        stiffness_matrix=stiffness,
        damping_matrix=damping,
        metadata=AnalysisMetadata(
            backend="direct_shear",
            response_definition="relative one-direction floor response",
            rayleigh_alpha=alpha,
            rayleigh_beta=beta,
            extras={"direction": model_config.direction},
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


def build_sensor_rows(config: ShearModelConfig, result: dict[str, np.ndarray]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sensor in config.sensors:
        story_index = sensor.story - 1
        for step, t in enumerate(result["time"]):
            disp = result["displacement"][step, story_index]
            vel = result["velocity"][step, story_index]
            acc = result["acceleration"][step, story_index]
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
                    "value": _project(sensor.quantity, disp, vel, acc),
                }
            )
    return rows


def _project(quantity: str, disp: float, vel: float, acc: float) -> float:
    if quantity in {"disp", "displacement"}:
        return float(disp)
    if quantity in {"vel", "velocity"}:
        return float(vel)
    return float(acc)


def write_outputs(result: dict[str, Any], output_dir: str | Path) -> None:
    write_shear_outputs(result, output_dir)
