"""Rayleigh beam matrix helpers built on Euler-Bernoulli stiffness."""

from __future__ import annotations

import numpy as np

from qrest_model.schema import BeamSectionConfig, GeometryConfig
from qrest_model.theory.euler_beam import (
    assemble_matrices as assemble_euler_matrices,
    base_excitation_load_vector as euler_base_excitation_load_vector,
    element_mass,
    element_stiffness,
)


def assemble_matrices(
    sections: tuple[BeamSectionConfig, ...],
    geometry: GeometryConfig,
) -> tuple[np.ndarray, np.ndarray]:
    mass, stiffness = assemble_euler_matrices(sections, geometry)
    return add_nodal_rotational_inertia(mass, sections), stiffness


def add_nodal_rotational_inertia(
    mass: np.ndarray,
    sections: tuple[BeamSectionConfig, ...],
) -> np.ndarray:
    result = np.asarray(mass, dtype=float).copy()
    expected = 2 * len(sections)
    if result.shape != (expected, expected):
        raise ValueError(f"Rayleigh beam mass matrix must have shape ({expected}, {expected}).")
    for index, section in enumerate(sections):
        inertia = section.rotational_inertia
        if not np.isfinite(inertia) or inertia < 0.0:
            raise ValueError("Rayleigh rotational_inertia values must be finite and non-negative.")
        result[2 * index + 1, 2 * index + 1] += inertia
    return result


def base_excitation_influence(
    sections: tuple[BeamSectionConfig, ...],
    geometry: GeometryConfig,
) -> np.ndarray:
    mass, _stiffness = assemble_matrices(sections, geometry)
    load_mass = base_excitation_load_vector(sections, geometry)
    return np.linalg.solve(mass, load_mass)


def base_excitation_load_vector(
    sections: tuple[BeamSectionConfig, ...],
    geometry: GeometryConfig,
) -> np.ndarray:
    return euler_base_excitation_load_vector(sections, geometry)


__all__ = [
    "add_nodal_rotational_inertia",
    "assemble_matrices",
    "base_excitation_influence",
    "base_excitation_load_vector",
    "element_mass",
    "element_stiffness",
]
