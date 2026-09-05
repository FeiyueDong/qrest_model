"""Damping utilities."""

from __future__ import annotations

import numpy as np

from qrest_model.analysis.modal import modal_analysis

from qrest_model.schema import DampingConfig


def rayleigh_coefficients(mass: np.ndarray, stiffness: np.ndarray, config: DampingConfig) -> tuple[float, float]:
    if config.zeta < 0.0:
        raise ValueError("Rayleigh damping ratio must be non-negative.")
    omegas = modal_analysis(mass, stiffness).omega
    if omegas.size < max(config.modes):
        raise ValueError("Not enough positive modes to compute Rayleigh damping.")
    w1 = omegas[config.modes[0] - 1]
    w2 = omegas[config.modes[1] - 1]
    matrix = np.array([[1.0 / (2.0 * w1), w1 / 2.0], [1.0 / (2.0 * w2), w2 / 2.0]])
    alpha, beta = np.linalg.solve(matrix, np.array([config.zeta, config.zeta]))
    return float(alpha), float(beta)


def rayleigh_matrix(mass: np.ndarray, stiffness: np.ndarray, config: DampingConfig) -> np.ndarray:
    alpha, beta = rayleigh_coefficients(mass, stiffness, config)
    return alpha * mass + beta * stiffness
