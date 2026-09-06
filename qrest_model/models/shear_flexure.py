"""Two-dimensional shear-flexure building model."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from qrest_model.analysis.validation import validate_positive_definite_matrix
from qrest_model.schema import GeometryConfig, ShearFlexureModelConfig, ShearFlexureStoryConfig
from qrest_model.theory.shear_flexure import assemble_matrices, base_excitation_influence


@dataclass(frozen=True)
class ShearFlexureBuilding2DModel:
    stories: tuple[ShearFlexureStoryConfig, ...]
    geometry: GeometryConfig

    @classmethod
    def from_config(cls, config: ShearFlexureModelConfig) -> "ShearFlexureBuilding2DModel":
        return cls(stories=config.stories, geometry=config.geometry)

    @property
    def num_stories(self) -> int:
        return len(self.stories)

    def mass_matrix(self) -> np.ndarray:
        mass, _stiffness = assemble_matrices(self.stories, self.geometry)
        return validate_positive_definite_matrix(
            mass,
            label="Shear-flexure global mass matrix",
        )

    def stiffness_matrix(self) -> np.ndarray:
        _mass, stiffness = assemble_matrices(self.stories, self.geometry)
        return validate_positive_definite_matrix(
            stiffness,
            label="Shear-flexure global stiffness matrix",
        )

    def influence_matrix(self) -> np.ndarray:
        return base_excitation_influence(self.stories, self.geometry)


__all__ = ["ShearFlexureBuilding2DModel"]
