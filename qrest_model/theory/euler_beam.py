"""Euler-Bernoulli beam element matrices and assembly helpers."""

from __future__ import annotations

import numpy as np

from qrest_model.schema import BeamSectionConfig, GeometryConfig


def element_stiffness(E: float, I: float, length: float) -> np.ndarray:
    _validate_positive(E, "E")
    _validate_positive(I, "I")
    _validate_positive(length, "length")
    L = float(length)
    scale = E * I / L**3
    return scale * np.array(
        [
            [12.0, 6.0 * L, -12.0, 6.0 * L],
            [6.0 * L, 4.0 * L**2, -6.0 * L, 2.0 * L**2],
            [-12.0, -6.0 * L, 12.0, -6.0 * L],
            [6.0 * L, 2.0 * L**2, -6.0 * L, 4.0 * L**2],
        ],
        dtype=float,
    )


def element_mass(density: float, area: float, length: float) -> np.ndarray:
    _validate_positive(density, "density")
    _validate_positive(area, "area")
    _validate_positive(length, "length")
    L = float(length)
    scale = density * area * L / 420.0
    return scale * np.array(
        [
            [156.0, 22.0 * L, 54.0, -13.0 * L],
            [22.0 * L, 4.0 * L**2, 13.0 * L, -3.0 * L**2],
            [54.0, 13.0 * L, 156.0, -22.0 * L],
            [-13.0 * L, -3.0 * L**2, -22.0 * L, 4.0 * L**2],
        ],
        dtype=float,
    )


def assemble_matrices(
    sections: tuple[BeamSectionConfig, ...],
    geometry: GeometryConfig,
) -> tuple[np.ndarray, np.ndarray]:
    mass, stiffness = assemble_full_matrices(sections, geometry)
    return mass[2:, 2:], stiffness[2:, 2:]


def assemble_full_matrices(
    sections: tuple[BeamSectionConfig, ...],
    geometry: GeometryConfig,
) -> tuple[np.ndarray, np.ndarray]:
    if len(sections) != len(geometry.story_heights):
        raise ValueError("Beam section count must match geometry.story_heights.")
    ndof_full = 2 * (len(sections) + 1)
    mass = np.zeros((ndof_full, ndof_full), dtype=float)
    stiffness = np.zeros((ndof_full, ndof_full), dtype=float)
    for index, (section, height) in enumerate(zip(sections, geometry.story_heights)):
        dofs = [2 * index, 2 * index + 1, 2 * index + 2, 2 * index + 3]
        ke = element_stiffness(section.E, section.I, height)
        me = element_mass(section.density, section.A, height)
        for local_i, global_i in enumerate(dofs):
            for local_j, global_j in enumerate(dofs):
                stiffness[global_i, global_j] += ke[local_i, local_j]
                mass[global_i, global_j] += me[local_i, local_j]
    return mass, stiffness


def base_excitation_influence(
    sections: tuple[BeamSectionConfig, ...],
    geometry: GeometryConfig,
) -> np.ndarray:
    free_mass = assemble_matrices(sections, geometry)[0]
    effective_load_mass = base_excitation_load_vector(sections, geometry)
    return np.linalg.solve(free_mass, effective_load_mass)


def base_excitation_load_vector(
    sections: tuple[BeamSectionConfig, ...],
    geometry: GeometryConfig,
) -> np.ndarray:
    full_mass, _stiffness = assemble_full_matrices(sections, geometry)
    free_mass = full_mass[2:, 2:]
    coupling_mass = full_mass[2:, :2]
    rigid_translation = np.zeros(full_mass.shape[0], dtype=float)
    rigid_translation[0::2] = 1.0
    return (
        free_mass @ rigid_translation[2:]
        + coupling_mass @ rigid_translation[:2]
    )


def _validate_positive(value: float, label: str) -> None:
    if not np.isfinite(value) or value <= 0.0:
        raise ValueError(f"Euler beam {label} must be positive and finite.")


__all__ = [
    "assemble_matrices",
    "assemble_full_matrices",
    "base_excitation_influence",
    "base_excitation_load_vector",
    "element_mass",
    "element_stiffness",
]
