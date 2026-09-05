"""Three-DOF rigid-floor shear building model."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from qrest_model.analysis.linear_system import LinearSystem
from qrest_model.schema import ModelConfig, StoryConfig
from qrest_model.theory.story_stiffness import assemble_global_stiffness, assemble_mass


@dataclass(frozen=True)
class RigidFloorBuildingModel:
    stories: tuple[StoryConfig, ...]

    @classmethod
    def from_config(cls, config: ModelConfig) -> "RigidFloorBuildingModel":
        return cls(stories=config.stories)

    @property
    def num_stories(self) -> int:
        return len(self.stories)

    def mass_matrix(self) -> np.ndarray:
        return assemble_mass(self.stories)

    def stiffness_matrix(self) -> np.ndarray:
        return assemble_global_stiffness(self.stories)

    def influence_matrix(self) -> np.ndarray:
        ux = np.tile(np.array([1.0, 0.0, 0.0]), self.num_stories)
        uy = np.tile(np.array([0.0, 1.0, 0.0]), self.num_stories)
        return np.column_stack([ux, uy])

    def linear_system(self, damping: np.ndarray) -> LinearSystem:
        return LinearSystem(
            mass=self.mass_matrix(),
            damping=damping,
            stiffness=self.stiffness_matrix(),
            influence=self.influence_matrix(),
        )

