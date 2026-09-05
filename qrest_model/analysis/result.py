"""Structured analysis result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from qrest_model.analysis.modal import ModalResult


@dataclass(frozen=True)
class ResponseHistory:
    displacement: np.ndarray
    velocity: np.ndarray
    acceleration: np.ndarray

    def __post_init__(self) -> None:
        displacement = np.asarray(self.displacement, dtype=float)
        velocity = np.asarray(self.velocity, dtype=float)
        acceleration = np.asarray(self.acceleration, dtype=float)
        if velocity.shape != displacement.shape or acceleration.shape != displacement.shape:
            raise ValueError("ResponseHistory arrays must have matching shapes.")
        object.__setattr__(self, "displacement", displacement)
        object.__setattr__(self, "velocity", velocity)
        object.__setattr__(self, "acceleration", acceleration)


@dataclass(frozen=True)
class SensorResult:
    rows: list[dict[str, Any]] = field(default_factory=list)
    displacement: tuple[np.ndarray, ...] | None = None
    velocity: tuple[np.ndarray, ...] | None = None
    acceleration: tuple[np.ndarray, ...] | None = None
    absolute_displacement: tuple[np.ndarray, ...] | None = None
    absolute_velocity: tuple[np.ndarray, ...] | None = None
    absolute_acceleration: tuple[np.ndarray, ...] | None = None


@dataclass(frozen=True)
class AnalysisMetadata:
    backend: str
    response_definition: str
    rayleigh_alpha: float | None = None
    rayleigh_beta: float | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "backend": self.backend,
            "response_definition": self.response_definition,
        }
        if self.rayleigh_alpha is not None:
            data["rayleigh_alpha"] = self.rayleigh_alpha
        if self.rayleigh_beta is not None:
            data["rayleigh_beta"] = self.rayleigh_beta
        data.update(self.extras)
        return data


@dataclass(frozen=True)
class AnalysisResult:
    time: np.ndarray
    relative: ResponseHistory
    mass_matrix: np.ndarray
    stiffness_matrix: np.ndarray
    damping_matrix: np.ndarray
    metadata: AnalysisMetadata
    absolute: ResponseHistory | None = None
    ground: ResponseHistory | None = None
    modal: ModalResult | None = None
    sensors: SensorResult | None = None
    story_stiffness_rows: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        time = np.asarray(self.time, dtype=float)
        if time.ndim != 1:
            raise ValueError("AnalysisResult.time must be one-dimensional.")
        if self.relative.displacement.shape[0] != time.size:
            raise ValueError("Response histories must have one row per time sample.")
        object.__setattr__(self, "time", time)
        object.__setattr__(self, "mass_matrix", np.asarray(self.mass_matrix, dtype=float))
        object.__setattr__(self, "stiffness_matrix", np.asarray(self.stiffness_matrix, dtype=float))
        object.__setattr__(self, "damping_matrix", np.asarray(self.damping_matrix, dtype=float))

    def to_legacy_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "time": self.time,
            "displacement": self.relative.displacement,
            "velocity": self.relative.velocity,
            "acceleration": self.relative.acceleration,
            "mass_matrix": self.mass_matrix,
            "stiffness_matrix": self.stiffness_matrix,
            "damping_matrix": self.damping_matrix,
            "metadata": self.metadata.to_dict(),
            "story_stiffness_rows": self.story_stiffness_rows,
        }
        if self.absolute is not None:
            data.update(
                {
                    "absolute_displacement": self.absolute.displacement,
                    "absolute_velocity": self.absolute.velocity,
                    "absolute_acceleration": self.absolute.acceleration,
                }
            )
        if self.ground is not None:
            data.update(
                {
                    "ground_displacement": self.ground.displacement,
                    "ground_velocity": self.ground.velocity,
                    "ground_acceleration": self.ground.acceleration,
                }
            )
        if self.sensors is not None:
            data["sensor_rows"] = self.sensors.rows
            _put_optional(data, "sensor_displacement", self.sensors.displacement)
            _put_optional(data, "sensor_velocity", self.sensors.velocity)
            _put_optional(data, "sensor_acceleration", self.sensors.acceleration)
            _put_optional(data, "sensor_absolute_displacement", self.sensors.absolute_displacement)
            _put_optional(data, "sensor_absolute_velocity", self.sensors.absolute_velocity)
            _put_optional(data, "sensor_absolute_acceleration", self.sensors.absolute_acceleration)
        else:
            data["sensor_rows"] = []
        return data


def _put_optional(data: dict[str, Any], key: str, value: Any | None) -> None:
    if value is not None:
        data[key] = value
