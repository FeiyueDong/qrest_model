"""Linear structural system representation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class LinearSystem:
    """Linear system M u_ddot + C u_dot + K u = -M Gamma a_g."""

    mass: np.ndarray
    damping: np.ndarray
    stiffness: np.ndarray
    influence: np.ndarray

    def __post_init__(self) -> None:
        mass = np.asarray(self.mass, dtype=float)
        damping = np.asarray(self.damping, dtype=float)
        stiffness = np.asarray(self.stiffness, dtype=float)
        influence = np.asarray(self.influence, dtype=float)
        if mass.ndim != 2 or mass.shape[0] != mass.shape[1]:
            raise ValueError("LinearSystem.mass must be a square matrix.")
        if damping.shape != mass.shape:
            raise ValueError("LinearSystem.damping must match mass shape.")
        if stiffness.shape != mass.shape:
            raise ValueError("LinearSystem.stiffness must match mass shape.")
        if influence.ndim == 1:
            influence = influence[:, None]
        if influence.ndim != 2 or influence.shape[0] != mass.shape[0]:
            raise ValueError("LinearSystem.influence must have one row per DOF.")
        object.__setattr__(self, "mass", mass)
        object.__setattr__(self, "damping", damping)
        object.__setattr__(self, "stiffness", stiffness)
        object.__setattr__(self, "influence", influence)

