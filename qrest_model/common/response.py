"""Response post-processing helpers."""

from __future__ import annotations

import numpy as np


def ground_kinematics(
    time: np.ndarray,
    ground_ax: np.ndarray,
    ground_ay: np.ndarray,
) -> dict[str, np.ndarray]:
    """Integrate ground acceleration to velocity and displacement.

    The integration assumes zero initial ground velocity and displacement.
    """

    vx = _integrate_trapezoid(time, ground_ax)
    vy = _integrate_trapezoid(time, ground_ay)
    ux = _integrate_trapezoid(time, vx)
    uy = _integrate_trapezoid(time, vy)
    return {
        "displacement": np.column_stack([ux, uy]),
        "velocity": np.column_stack([vx, vy]),
        "acceleration": np.column_stack([ground_ax, ground_ay]),
    }


def add_absolute_floor_response(
    response: dict,
    ground_ax: np.ndarray,
    ground_ay: np.ndarray,
) -> None:
    ground = ground_kinematics(response["time"], ground_ax, ground_ay)
    response["ground_displacement"] = ground["displacement"]
    response["ground_velocity"] = ground["velocity"]
    response["ground_acceleration"] = ground["acceleration"]
    response["ground_displacement_source"] = "integrated_from_acceleration"
    response["ground_velocity_source"] = "integrated_from_acceleration"
    response["absolute_displacement"] = _add_ground(response["displacement"], ground["displacement"])
    response["absolute_velocity"] = _add_ground(response["velocity"], ground["velocity"])
    response["absolute_acceleration"] = _add_ground(response["acceleration"], ground["acceleration"])


def add_absolute_shear_response(
    response: dict,
    ground_ax: np.ndarray,
    ground_ay: np.ndarray,
    direction: str,
) -> None:
    ground = ground_kinematics(response["time"], ground_ax, ground_ay)
    response["ground_displacement"] = ground["displacement"]
    response["ground_velocity"] = ground["velocity"]
    response["ground_acceleration"] = ground["acceleration"]
    response["ground_displacement_source"] = "integrated_from_acceleration"
    response["ground_velocity_source"] = "integrated_from_acceleration"
    ground_index = 0 if direction.upper() == "X" else 1
    response["absolute_displacement"] = response["displacement"] + ground["displacement"][:, ground_index, None]
    response["absolute_velocity"] = response["velocity"] + ground["velocity"][:, ground_index, None]
    response["absolute_acceleration"] = response["acceleration"] + ground["acceleration"][:, ground_index, None]


def add_absolute_beam_response(
    response: dict,
    ground_ax: np.ndarray,
    ground_ay: np.ndarray,
) -> None:
    ground = ground_kinematics(response["time"], ground_ax, ground_ay)
    response["ground_displacement"] = ground["displacement"]
    response["ground_velocity"] = ground["velocity"]
    response["ground_acceleration"] = ground["acceleration"]
    response["ground_displacement_source"] = "integrated_from_acceleration"
    response["ground_velocity_source"] = "integrated_from_acceleration"
    response["absolute_displacement"] = _add_ground_to_beam_u(response["displacement"], ground["displacement"][:, 0])
    response["absolute_velocity"] = _add_ground_to_beam_u(response["velocity"], ground["velocity"][:, 0])
    response["absolute_acceleration"] = _add_ground_to_beam_u(response["acceleration"], ground["acceleration"][:, 0])


def _integrate_trapezoid(time: np.ndarray, values: np.ndarray) -> np.ndarray:
    integrated = np.zeros_like(values, dtype=float)
    for i in range(1, values.size):
        dt = float(time[i] - time[i - 1])
        integrated[i] = integrated[i - 1] + 0.5 * dt * (values[i - 1] + values[i])
    return integrated


def _add_ground(response: np.ndarray, ground_xy: np.ndarray) -> np.ndarray:
    absolute = response.copy()
    absolute[:, :, 0] += ground_xy[:, 0, None]
    absolute[:, :, 1] += ground_xy[:, 1, None]
    return absolute


def _add_ground_to_beam_u(response: np.ndarray, ground_u: np.ndarray) -> np.ndarray:
    absolute = response.copy()
    absolute[:, :, 0] += ground_u[:, None]
    return absolute
