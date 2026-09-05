"""Numerical validation helpers for linear structural models."""

from __future__ import annotations

import numpy as np


def validate_symmetric_matrix(
    matrix: np.ndarray,
    *,
    label: str,
    rtol: float = 1.0e-8,
    atol: float = 1.0e-10,
) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError(f"{label} must be a square matrix.")
    if not np.all(np.isfinite(matrix)):
        raise ValueError(f"{label} must be finite.")
    if not np.allclose(matrix, matrix.T, rtol=rtol, atol=atol):
        raise ValueError(f"{label} must be symmetric.")
    return matrix


def validate_positive_definite_matrix(
    matrix: np.ndarray,
    *,
    label: str,
    tolerance: float = 1.0e-8,
) -> np.ndarray:
    matrix = validate_symmetric_matrix(matrix, label=label)
    eigenvalues = np.linalg.eigvalsh(matrix)
    minimum = float(eigenvalues[0])
    if minimum <= tolerance:
        raise ValueError(
            f"{label} is singular or not positive definite; minimum eigenvalue is {minimum:.6e}."
        )
    return matrix


__all__ = ["validate_positive_definite_matrix", "validate_symmetric_matrix"]
