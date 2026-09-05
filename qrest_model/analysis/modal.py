"""Modal analysis helpers for linear structural systems."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.linalg import eigh


@dataclass(frozen=True)
class ModalResult:
    eigenvalues: np.ndarray
    omega: np.ndarray
    frequency: np.ndarray
    period: np.ndarray
    mode_shapes: np.ndarray


def modal_analysis(mass: np.ndarray, stiffness: np.ndarray, *, tolerance: float = 1.0e-8) -> ModalResult:
    mass = np.asarray(mass, dtype=float)
    stiffness = np.asarray(stiffness, dtype=float)
    if mass.ndim != 2 or mass.shape[0] != mass.shape[1]:
        raise ValueError("mass must be a square matrix.")
    if stiffness.shape != mass.shape:
        raise ValueError("stiffness must match mass shape.")
    if not np.all(np.isfinite(mass)) or not np.all(np.isfinite(stiffness)):
        raise ValueError("mass and stiffness matrices must be finite.")

    eigenvalues, eigenvectors = eigh(stiffness, mass)
    positive = eigenvalues > tolerance
    eigenvalues = eigenvalues[positive]
    mode_shapes = eigenvectors[:, positive]
    omega = np.sqrt(eigenvalues)

    for col in range(mode_shapes.shape[1]):
        mode = mode_shapes[:, col]
        norm = float(np.sqrt(abs(mode.T @ mass @ mode)))
        if norm > 0.0:
            mode = mode / norm
        pivot = int(np.argmax(np.abs(mode)))
        if mode[pivot] < 0.0:
            mode = -mode
        mode_shapes[:, col] = mode

    frequency = omega / (2.0 * np.pi)
    period = np.divide(
        2.0 * np.pi,
        omega,
        out=np.full_like(omega, np.inf, dtype=float),
        where=omega > 0.0,
    )
    return ModalResult(
        eigenvalues=eigenvalues,
        omega=omega,
        frequency=frequency,
        period=period,
        mode_shapes=mode_shapes,
    )
