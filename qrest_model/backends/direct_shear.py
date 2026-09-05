"""Direct matrix backend for one-direction shear-building models."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from qrest_model.common.damping import rayleigh_coefficients, rayleigh_matrix
from qrest_model.common.ground_motion import load_ground_motion
from qrest_model.common.io import ensure_output_dir, write_matrix, write_metadata, write_sensor_csv
from qrest_model.common.shear_config import ShearModelConfig, load_shear_config
from qrest_model.theory.shear_stiffness import (
    assemble_shear_mass,
    assemble_shear_stiffness,
    shear_story_stiffness_table,
)


def run(config: ShearModelConfig | str | Path, output_dir: str | Path | None = None) -> dict[str, Any]:
    if not isinstance(config, ShearModelConfig):
        config_path = Path(config)
        model_config = load_shear_config(config_path)
        base_dir = config_path.parent
    else:
        model_config = config
        base_dir = Path(".")

    ground = load_ground_motion(model_config.ground_motion, base_dir)
    ground_accel = ground["ax"] if model_config.direction == "X" else ground["ay"]
    mass = assemble_shear_mass(model_config.stories)
    stiffness = assemble_shear_stiffness(model_config.stories)
    damping = rayleigh_matrix(mass, stiffness, model_config.damping)
    alpha, beta = rayleigh_coefficients(mass, stiffness, model_config.damping)

    response = solve_newmark(
        mass=mass,
        damping=damping,
        stiffness=stiffness,
        time=ground["time"],
        ground_accel=ground_accel,
    )
    response.update(
        {
            "sensor_rows": build_sensor_rows(model_config, response),
            "mass_matrix": mass,
            "stiffness_matrix": stiffness,
            "damping_matrix": damping,
            "story_stiffness_rows": shear_story_stiffness_table(model_config.stories),
            "metadata": {
                "backend": "direct_shear",
                "direction": model_config.direction,
                "response_definition": "relative one-direction floor response",
                "rayleigh_alpha": alpha,
                "rayleigh_beta": beta,
            },
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
    ground_accel: np.ndarray,
    beta: float = 0.25,
    gamma: float = 0.5,
) -> dict[str, np.ndarray]:
    n_steps = time.size
    n = mass.shape[0]
    dt = float(time[1] - time[0])
    influence = np.ones(n, dtype=float)
    loads = -(mass @ influence)[:, None] * ground_accel[None, :]
    loads = loads.T

    disp = np.zeros((n_steps, n), dtype=float)
    vel = np.zeros((n_steps, n), dtype=float)
    acc = np.zeros((n_steps, n), dtype=float)
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
    return {"time": time, "displacement": disp, "velocity": vel, "acceleration": acc}


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
    output = ensure_output_dir(output_dir)
    write_shear_master_csv(output / "master_response.csv", result)
    write_sensor_csv(output / "sensor_response.csv", result["sensor_rows"])
    write_matrix(output / "mass_matrix.txt", result["mass_matrix"])
    write_matrix(output / "stiffness_matrix.txt", result["stiffness_matrix"])
    write_matrix(output / "damping_matrix.txt", result["damping_matrix"])
    write_sensor_csv(output / "story_stiffness_theory.txt", result["story_stiffness_rows"])
    write_metadata(output / "metadata.txt", result["metadata"])


def write_shear_master_csv(path: str | Path, result: dict[str, np.ndarray]) -> None:
    rows: list[dict[str, Any]] = []
    for step, t in enumerate(result["time"]):
        for story_index in range(result["displacement"].shape[1]):
            rows.append(
                {
                    "time": t,
                    "story": story_index + 1,
                    "node_or_sensor_id": f"story_{story_index + 1}",
                    "u": result["displacement"][step, story_index],
                    "v": result["velocity"][step, story_index],
                    "a": result["acceleration"][step, story_index],
                }
            )
    write_sensor_csv(path, rows)

