"""Two-dimensional Timoshenko beam building model."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from qrest_model.analysis.validation import validate_positive_definite_matrix
from qrest_model.schema import BeamSectionConfig, GeometryConfig, TimoshenkoBeamModelConfig
from qrest_model.theory.timoshenko_beam import assemble_matrices, base_excitation_influence


@dataclass(frozen=True)
class TimoshenkoBeam2DModel:
    sections: tuple[BeamSectionConfig, ...]
    geometry: GeometryConfig

    @classmethod
    def from_config(cls, config: TimoshenkoBeamModelConfig) -> "TimoshenkoBeam2DModel":
        return cls(sections=config.sections, geometry=config.geometry)

    @property
    def num_stories(self) -> int:
        return len(self.sections)

    def mass_matrix(self) -> np.ndarray:
        mass, _stiffness = assemble_matrices(self.sections, self.geometry)
        return validate_positive_definite_matrix(
            mass,
            label="Timoshenko beam global mass matrix",
        )

    def stiffness_matrix(self) -> np.ndarray:
        _mass, stiffness = assemble_matrices(self.sections, self.geometry)
        return validate_positive_definite_matrix(
            stiffness,
            label="Timoshenko beam global stiffness matrix",
        )

    def influence_matrix(self) -> np.ndarray:
        return base_excitation_influence(self.sections, self.geometry)


__all__ = ["TimoshenkoBeam2DModel"]
