"""Shear-flexure building element matrices and assembly helpers."""

from __future__ import annotations

import numpy as np

from qrest_model.schema import GeometryConfig, ShearFlexureStoryConfig
from qrest_model.theory.euler_beam import element_mass as flexural_element_mass
from qrest_model.theory.euler_beam import element_stiffness as flexural_element_stiffness


def shear_element_stiffness(shear_stiffness: float) -> np.ndarray:
    if not np.isfinite(shear_stiffness) or shear_stiffness < 0.0:
        raise ValueError("Shear-flexure shear_stiffness must be finite and non-negative.")
    return float(shear_stiffness) * np.array(
        [
            [1.0, 0.0, -1.0, 0.0],
            [0.0, 0.0, 0.0, 0.0],
            [-1.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 0.0],
        ],
        dtype=float,
    )


def element_stiffness(E: float, I: float, length: float, shear_stiffness: float) -> np.ndarray:
    return flexural_element_stiffness(E, I, length) + shear_element_stiffness(shear_stiffness)


def element_mass(density: float, area: float, length: float) -> np.ndarray:
    return flexural_element_mass(density, area, length)


def assemble_matrices(
    stories: tuple[ShearFlexureStoryConfig, ...],
    geometry: GeometryConfig,
) -> tuple[np.ndarray, np.ndarray]:
    mass, stiffness = assemble_full_matrices(stories, geometry)
    return mass[2:, 2:], stiffness[2:, 2:]


def assemble_full_matrices(
    stories: tuple[ShearFlexureStoryConfig, ...],
    geometry: GeometryConfig,
) -> tuple[np.ndarray, np.ndarray]:
    if len(stories) != len(geometry.story_heights):
        raise ValueError("Shear-flexure story count must match geometry.story_heights.")
    ndof_full = 2 * (len(stories) + 1)
    mass = np.zeros((ndof_full, ndof_full), dtype=float)
    stiffness = np.zeros((ndof_full, ndof_full), dtype=float)
    for index, (story, height) in enumerate(zip(stories, geometry.story_heights)):
        section = story.flexural_section
        dofs = [2 * index, 2 * index + 1, 2 * index + 2, 2 * index + 3]
        ke = element_stiffness(section.E, section.I, height, story.shear_stiffness)
        me = element_mass(section.density, section.A, height)
        for local_i, global_i in enumerate(dofs):
            for local_j, global_j in enumerate(dofs):
                stiffness[global_i, global_j] += ke[local_i, local_j]
                mass[global_i, global_j] += me[local_i, local_j]
    return mass, stiffness


def base_excitation_influence(
    stories: tuple[ShearFlexureStoryConfig, ...],
    geometry: GeometryConfig,
) -> np.ndarray:
    mass, _stiffness = assemble_matrices(stories, geometry)
    load_mass = base_excitation_load_vector(stories, geometry)
    return np.linalg.solve(mass, load_mass)


def base_excitation_load_vector(
    stories: tuple[ShearFlexureStoryConfig, ...],
    geometry: GeometryConfig,
) -> np.ndarray:
    full_mass, _stiffness = assemble_full_matrices(stories, geometry)
    free_mass = full_mass[2:, 2:]
    coupling_mass = full_mass[2:, :2]
    rigid_translation = np.zeros(full_mass.shape[0], dtype=float)
    rigid_translation[0::2] = 1.0
    return (
        free_mass @ rigid_translation[2:]
        + coupling_mass @ rigid_translation[:2]
    )


__all__ = [
    "assemble_full_matrices",
    "assemble_matrices",
    "base_excitation_influence",
    "base_excitation_load_vector",
    "element_mass",
    "element_stiffness",
    "shear_element_stiffness",
]
