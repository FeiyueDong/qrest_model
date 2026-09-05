"""Shared linear direct-backend workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from qrest_model.analysis.modal import ModalResult, modal_analysis
from qrest_model.analysis.newmark import NewmarkSolver
from qrest_model.analysis.linear_system import LinearSystem
from qrest_model.common.damping import rayleigh_coefficients
from qrest_model.schema import DampingConfig


class LinearStructuralModel(Protocol):
    def mass_matrix(self) -> np.ndarray:
        ...

    def stiffness_matrix(self) -> np.ndarray:
        ...

    def influence_matrix(self) -> np.ndarray:
        ...


@dataclass(frozen=True)
class LinearDirectResult:
    time: np.ndarray
    displacement: np.ndarray
    velocity: np.ndarray
    acceleration: np.ndarray
    mass_matrix: np.ndarray
    stiffness_matrix: np.ndarray
    damping_matrix: np.ndarray
    modal: ModalResult
    rayleigh_alpha: float
    rayleigh_beta: float


def run_linear_direct(
    model: LinearStructuralModel,
    damping_config: DampingConfig,
    time: np.ndarray,
    ground_acceleration: np.ndarray,
    *,
    beta: float = 0.25,
    gamma: float = 0.5,
) -> LinearDirectResult:
    mass = model.mass_matrix()
    stiffness = model.stiffness_matrix()
    alpha, rayleigh_beta = rayleigh_coefficients(mass, stiffness, damping_config)
    damping = alpha * mass + rayleigh_beta * stiffness
    system = LinearSystem(
        mass=mass,
        damping=damping,
        stiffness=stiffness,
        influence=model.influence_matrix(),
    )
    result = NewmarkSolver(beta=beta, gamma=gamma).solve(system, time, ground_acceleration)
    return LinearDirectResult(
        time=result.time,
        displacement=result.displacement,
        velocity=result.velocity,
        acceleration=result.acceleration,
        mass_matrix=mass,
        stiffness_matrix=stiffness,
        damping_matrix=damping,
        modal=modal_analysis(mass, stiffness),
        rayleigh_alpha=alpha,
        rayleigh_beta=rayleigh_beta,
    )


__all__ = ["LinearDirectResult", "run_linear_direct"]
