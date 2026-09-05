"""Direct stiffness backend for qREST controllable structural models."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from qrest_model.common.config import ModelConfig, load_config
from qrest_model.common.damping import rayleigh_coefficients, rayleigh_matrix
from qrest_model.common.ground_motion import load_ground_motion
from qrest_model.common.io import (
    ensure_output_dir,
    write_master_csv,
    write_matrix,
    write_metadata,
    write_sensor_csv,
)
from qrest_model.common.response import add_absolute_floor_response
from qrest_model.theory.sensor_mapping import build_sensor_rows
from qrest_model.theory.story_stiffness import (
    assemble_global_stiffness,
    assemble_mass,
    story_stiffness_table,
)


def run(config: ModelConfig | str | Path, output_dir: str | Path | None = None) -> dict[str, Any]:
    if not isinstance(config, ModelConfig):
        config_path = Path(config)
        model_config = load_config(config_path)
        base_dir = config_path.parent
    else:
        model_config = config
        base_dir = Path(".")

    ground = load_ground_motion(model_config.ground_motion, base_dir)
    mass = assemble_mass(model_config.stories)
    stiffness = assemble_global_stiffness(model_config.stories)
    damping = rayleigh_matrix(mass, stiffness, model_config.damping)
    alpha, beta = rayleigh_coefficients(mass, stiffness, model_config.damping)

    response = solve_newmark(
        mass=mass,
        damping=damping,
        stiffness=stiffness,
        time=ground["time"],
        ground_ax=ground["ax"],
        ground_ay=ground["ay"],
        num_stories=model_config.num_stories,
    )
    add_absolute_floor_response(response, ground["ax"], ground["ay"])
    sensor_rows = build_sensor_rows(
        model_config.sensors,
        response["time"],
        response["displacement"],
        response["velocity"],
        response["acceleration"],
        response["absolute_displacement"],
        response["absolute_velocity"],
        response["absolute_acceleration"],
    )
    response.update(
        {
            "sensor_rows": sensor_rows,
            "mass_matrix": mass,
            "stiffness_matrix": stiffness,
            "damping_matrix": damping,
            "metadata": {
                "backend": "direct_stiffness",
                "response_definition": "ux/uy/rz, vx/vy/vrz, ax/ay/arz are relative response; abs_* columns include ground translation from integrated input acceleration",
                "rayleigh_alpha": alpha,
                "rayleigh_beta": beta,
            },
            "story_stiffness_rows": story_stiffness_table(model_config.stories),
        }
    )

    if output_dir is not None:
        write_outputs(response, output_dir)
    return response


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
    ndof = mass.shape[0]
    dt = float(time[1] - time[0])
    n_steps = time.size
    ux_influence = np.tile(np.array([1.0, 0.0, 0.0]), num_stories)
    uy_influence = np.tile(np.array([0.0, 1.0, 0.0]), num_stories)
    loads = -mass @ (np.outer(ground_ax, ux_influence).T + np.outer(ground_ay, uy_influence).T)
    loads = loads.T

    disp = np.zeros((n_steps, ndof), dtype=float)
    vel = np.zeros((n_steps, ndof), dtype=float)
    acc = np.zeros((n_steps, ndof), dtype=float)
    acc[0] = np.linalg.solve(mass, loads[0] - damping @ vel[0] - stiffness @ disp[0])

    k_eff = stiffness + gamma / (beta * dt) * damping + mass / (beta * dt * dt)
    for i in range(n_steps - 1):
        rhs = (
            loads[i + 1]
            + mass
            @ (
                disp[i] / (beta * dt * dt)
                + vel[i] / (beta * dt)
                + (1.0 / (2.0 * beta) - 1.0) * acc[i]
            )
            + damping
            @ (
                gamma * disp[i] / (beta * dt)
                + (gamma / beta - 1.0) * vel[i]
                + dt * (gamma / (2.0 * beta) - 1.0) * acc[i]
            )
        )
        disp[i + 1] = np.linalg.solve(k_eff, rhs)
        acc[i + 1] = (
            (disp[i + 1] - disp[i]) / (beta * dt * dt)
            - vel[i] / (beta * dt)
            - (1.0 / (2.0 * beta) - 1.0) * acc[i]
        )
        vel[i + 1] = vel[i] + dt * ((1.0 - gamma) * acc[i] + gamma * acc[i + 1])

    shaped = {
        "time": time,
        "displacement": disp.reshape((n_steps, num_stories, 3)),
        "velocity": vel.reshape((n_steps, num_stories, 3)),
        "acceleration": acc.reshape((n_steps, num_stories, 3)),
    }
    return shaped


def write_outputs(result: dict[str, Any], output_dir: str | Path) -> None:
    output = ensure_output_dir(output_dir)
    write_master_csv(output / "master_response.csv", result)
    write_sensor_csv(output / "sensor_response.csv", result["sensor_rows"])
    write_matrix(output / "mass_matrix.txt", result["mass_matrix"])
    write_matrix(output / "stiffness_matrix.txt", result["stiffness_matrix"])
    write_matrix(output / "damping_matrix.txt", result["damping_matrix"])
    write_sensor_csv(output / "story_stiffness_theory.txt", result["story_stiffness_rows"])
    write_metadata(output / "metadata.txt", result["metadata"])
