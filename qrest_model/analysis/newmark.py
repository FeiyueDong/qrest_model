"""Linear Newmark time integration."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.linalg import lu_factor, lu_solve

from qrest_model.analysis.linear_system import LinearSystem


@dataclass(frozen=True)
class NewmarkResult:
    time: np.ndarray
    displacement: np.ndarray
    velocity: np.ndarray
    acceleration: np.ndarray


@dataclass(frozen=True)
class NewmarkSolver:
    beta: float = 0.25
    gamma: float = 0.5

    def solve(
        self,
        system: LinearSystem,
        time: np.ndarray,
        ground_acceleration: np.ndarray,
        *,
        initial_displacement: np.ndarray | None = None,
        initial_velocity: np.ndarray | None = None,
    ) -> NewmarkResult:
        time = np.asarray(time, dtype=float)
        if time.ndim != 1 or time.size < 2:
            raise ValueError("Newmark time must be a one-dimensional array with at least two samples.")
        dt = _constant_time_step(time)

        ground_acceleration = np.asarray(ground_acceleration, dtype=float)
        if ground_acceleration.ndim == 1:
            ground_acceleration = ground_acceleration[:, None]
        if ground_acceleration.shape[0] != time.size:
            raise ValueError("ground_acceleration must have one row per time sample.")
        if ground_acceleration.shape[1] != system.influence.shape[1]:
            raise ValueError("ground_acceleration component count must match system influence columns.")
        if not np.all(np.isfinite(ground_acceleration)):
            raise ValueError("ground_acceleration must be finite.")

        n_steps = time.size
        ndof = system.mass.shape[0]
        disp = _initial_vector(initial_displacement, ndof, "initial_displacement")
        vel = _initial_vector(initial_velocity, ndof, "initial_velocity")
        acc = np.zeros(ndof, dtype=float)

        effective_ground = ground_acceleration @ system.influence.T
        loads = -(system.mass @ effective_ground.T).T

        displacement = np.zeros((n_steps, ndof), dtype=float)
        velocity = np.zeros_like(displacement)
        acceleration = np.zeros_like(displacement)
        displacement[0] = disp
        velocity[0] = vel
        acceleration[0] = np.linalg.solve(
            system.mass,
            loads[0] - system.damping @ velocity[0] - system.stiffness @ displacement[0],
        )

        beta = self.beta
        gamma = self.gamma
        if beta <= 0.0 or gamma <= 0.0:
            raise ValueError("Newmark beta and gamma must be positive.")
        k_eff = system.stiffness + gamma / (beta * dt) * system.damping + system.mass / (beta * dt * dt)
        factor = lu_factor(k_eff)

        for i in range(n_steps - 1):
            rhs = (
                loads[i + 1]
                + system.mass
                @ (
                    displacement[i] / (beta * dt * dt)
                    + velocity[i] / (beta * dt)
                    + (1.0 / (2.0 * beta) - 1.0) * acceleration[i]
                )
                + system.damping
                @ (
                    gamma * displacement[i] / (beta * dt)
                    + (gamma / beta - 1.0) * velocity[i]
                    + dt * (gamma / (2.0 * beta) - 1.0) * acceleration[i]
                )
            )
            displacement[i + 1] = lu_solve(factor, rhs)
            acceleration[i + 1] = (
                (displacement[i + 1] - displacement[i]) / (beta * dt * dt)
                - velocity[i] / (beta * dt)
                - (1.0 / (2.0 * beta) - 1.0) * acceleration[i]
            )
            velocity[i + 1] = velocity[i] + dt * (
                (1.0 - gamma) * acceleration[i] + gamma * acceleration[i + 1]
            )

        return NewmarkResult(
            time=time,
            displacement=displacement,
            velocity=velocity,
            acceleration=acceleration,
        )


def _constant_time_step(time: np.ndarray) -> float:
    if not np.all(np.isfinite(time)):
        raise ValueError("Newmark time values must be finite.")
    dt = np.diff(time)
    if np.any(dt <= 0.0):
        raise ValueError("Newmark time values must be strictly increasing.")
    if not np.allclose(dt, dt[0], rtol=1.0e-9, atol=1.0e-12):
        raise ValueError("Newmark time step must be constant.")
    return float(dt[0])


def _initial_vector(value: np.ndarray | None, size: int, label: str) -> np.ndarray:
    if value is None:
        return np.zeros(size, dtype=float)
    vector = np.asarray(value, dtype=float)
    if vector.shape != (size,):
        raise ValueError(f"{label} must have shape ({size},).")
    if not np.all(np.isfinite(vector)):
        raise ValueError(f"{label} must be finite.")
    return vector.copy()

