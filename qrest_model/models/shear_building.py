"""One-direction shear building model."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from qrest_model.analysis.linear_system import LinearSystem
from qrest_model.analysis.validation import validate_positive_definite_matrix
from qrest_model.schema import ShearModelConfig, ShearStoryConfig
from qrest_model.theory.shear_stiffness import assemble_shear_mass, assemble_shear_stiffness


@dataclass(frozen=True)
class ShearBuildingModel:
    stories: tuple[ShearStoryConfig, ...]
    direction: str

    @classmethod
    def from_config(cls, config: ShearModelConfig) -> "ShearBuildingModel":
        return cls(stories=config.stories, direction=config.direction)

    @property
    def num_stories(self) -> int:
        return len(self.stories)

    def mass_matrix(self) -> np.ndarray:
        return validate_positive_definite_matrix(
            assemble_shear_mass(self.stories),
            label="Shear-building global mass matrix",
        )

    def stiffness_matrix(self) -> np.ndarray:
        return validate_positive_definite_matrix(
            assemble_shear_stiffness(self.stories),
            label="Shear-building global stiffness matrix",
        )

    def influence_matrix(self) -> np.ndarray:
        return np.ones(self.num_stories, dtype=float)

    def linear_system(self, damping: np.ndarray) -> LinearSystem:
        return LinearSystem(
            mass=self.mass_matrix(),
            damping=damping,
            stiffness=self.stiffness_matrix(),
            influence=self.influence_matrix(),
        )
