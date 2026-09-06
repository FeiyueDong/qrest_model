"""Timoshenko beam element matrices and assembly helpers."""

from __future__ import annotations

import numpy as np

from qrest_model.schema import BeamSectionConfig, GeometryConfig
from qrest_model.theory.rayleigh_beam import add_nodal_rotational_inertia


def element_stiffness(E: float, G: float, area: float, shear_area: float, I: float, length: float) -> np.ndarray:
    _validate_positive(E, "E")
    _validate_positive(G, "G")
    _validate_positive(area, "area")
    _validate_positive(shear_area, "shear_area")
    _validate_positive(I, "I")
    _validate_positive(length, "length")
    L = float(length)
    phi = 12.0 * E * I / (G * shear_area * L**2)
    scale = E * I / (L**3 * (1.0 + phi))
    return scale * np.array(
        [
            [12.0, 6.0 * L, -12.0, 6.0 * L],
            [6.0 * L, (4.0 + phi) * L**2, -6.0 * L, (2.0 - phi) * L**2],
            [-12.0, -6.0 * L, 12.0, -6.0 * L],
            [6.0 * L, (2.0 - phi) * L**2, -6.0 * L, (4.0 + phi) * L**2],
        ],
        dtype=float,
    )


def element_mass(E: float, G: float, area: float, shear_area: float, I: float, density: float, length: float) -> np.ndarray:
    _validate_positive(E, "E")
    _validate_positive(G, "G")
    _validate_positive(area, "area")
    _validate_positive(shear_area, "shear_area")
    _validate_positive(I, "I")
    _validate_positive(density, "density")
    _validate_positive(length, "length")
    L = float(length)
    phi = 12.0 * E * I / (G * shear_area * L**2)
    mass_per_length = density * area
    c1z = mass_per_length * L / (210.0 * (1.0 + phi) ** 2)
    translational = c1z * np.array(
        [
            [70.0 * phi**2 + 147.0 * phi + 78.0, L / 4.0 * (35.0 * phi**2 + 77.0 * phi + 44.0), 35.0 * phi**2 + 63.0 * phi + 27.0, -L / 4.0 * (35.0 * phi**2 + 63.0 * phi + 26.0)],
            [L / 4.0 * (35.0 * phi**2 + 77.0 * phi + 44.0), L**2 / 4.0 * (7.0 * phi**2 + 14.0 * phi + 8.0), L / 4.0 * (35.0 * phi**2 + 63.0 * phi + 26.0), -L**2 / 4.0 * (7.0 * phi**2 + 14.0 * phi + 6.0)],
            [35.0 * phi**2 + 63.0 * phi + 27.0, L / 4.0 * (35.0 * phi**2 + 63.0 * phi + 26.0), 70.0 * phi**2 + 147.0 * phi + 78.0, -L / 4.0 * (35.0 * phi**2 + 77.0 * phi + 44.0)],
            [-L / 4.0 * (35.0 * phi**2 + 63.0 * phi + 26.0), -L**2 / 4.0 * (7.0 * phi**2 + 14.0 * phi + 6.0), -L / 4.0 * (35.0 * phi**2 + 77.0 * phi + 44.0), L**2 / 4.0 * (7.0 * phi**2 + 14.0 * phi + 8.0)],
        ],
        dtype=float,
    )
    c2z = density * I / (30.0 * L * (1.0 + phi) ** 2)
    rotary = c2z * np.array(
        [
            [36.0, -L * (15.0 * phi - 3.0), -36.0, -L * (15.0 * phi - 3.0)],
            [-L * (15.0 * phi - 3.0), L**2 * (10.0 * phi**2 + 5.0 * phi + 4.0), L * (15.0 * phi - 3.0), L**2 * (5.0 * phi**2 - 5.0 * phi - 1.0)],
            [-36.0, L * (15.0 * phi - 3.0), 36.0, L * (15.0 * phi - 3.0)],
            [-L * (15.0 * phi - 3.0), L**2 * (5.0 * phi**2 - 5.0 * phi - 1.0), L * (15.0 * phi - 3.0), L**2 * (10.0 * phi**2 + 5.0 * phi + 4.0)],
        ],
        dtype=float,
    )
    return translational + rotary


def assemble_matrices(
    sections: tuple[BeamSectionConfig, ...],
    geometry: GeometryConfig,
) -> tuple[np.ndarray, np.ndarray]:
    mass, stiffness = assemble_full_matrices_with_timoshenko_stiffness(sections, geometry)
    return mass[2:, 2:], stiffness[2:, 2:]


def assemble_full_matrices_with_timoshenko_stiffness(
    sections: tuple[BeamSectionConfig, ...],
    geometry: GeometryConfig,
) -> tuple[np.ndarray, np.ndarray]:
    if len(sections) != len(geometry.story_heights):
        raise ValueError("Beam section count must match geometry.story_heights.")
    ndof_full = 2 * (len(sections) + 1)
    mass = np.zeros((ndof_full, ndof_full), dtype=float)
    stiffness = np.zeros((ndof_full, ndof_full), dtype=float)
    for index, (section, height) in enumerate(zip(sections, geometry.story_heights)):
        if section.G is None or section.shear_area is None:
            raise ValueError("Timoshenko beam sections require G and shear_area.")
        dofs = [2 * index, 2 * index + 1, 2 * index + 2, 2 * index + 3]
        ke = element_stiffness(section.E, section.G, section.A, section.shear_area, section.I, height)
        me = element_mass(section.E, section.G, section.A, section.shear_area, section.I, section.density, height)
        for local_i, global_i in enumerate(dofs):
            for local_j, global_j in enumerate(dofs):
                stiffness[global_i, global_j] += ke[local_i, local_j]
                mass[global_i, global_j] += me[local_i, local_j]
    mass[2:, 2:] = add_nodal_rotational_inertia(mass[2:, 2:], sections)
    return mass, stiffness


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
    full_mass, _stiffness = assemble_full_matrices_with_timoshenko_stiffness(sections, geometry)
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
        raise ValueError(f"Timoshenko beam {label} must be positive and finite.")


__all__ = [
    "assemble_full_matrices_with_timoshenko_stiffness",
    "assemble_matrices",
    "base_excitation_influence",
    "base_excitation_load_vector",
    "element_mass",
    "element_stiffness",
]
