"""Structured analysis result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from qrest_model.analysis.modal import ModalResult


def _canonical_quantity(quantity: str) -> str:
    normalized = quantity.lower()
    if normalized in {"disp", "displacement"}:
        return "displacement"
    if normalized in {"vel", "velocity"}:
        return "velocity"
    if normalized in {"accel", "acceleration"}:
        return "acceleration"
    raise ValueError(f"Unsupported observation quantity: {quantity}")


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
        if not np.all(np.isfinite(displacement)):
            raise ValueError("ResponseHistory.displacement must be finite.")
        if not np.all(np.isfinite(velocity)):
            raise ValueError("ResponseHistory.velocity must be finite.")
        if not np.all(np.isfinite(acceleration)):
            raise ValueError("ResponseHistory.acceleration must be finite.")
        object.__setattr__(self, "displacement", displacement)
        object.__setattr__(self, "velocity", velocity)
        object.__setattr__(self, "acceleration", acceleration)


@dataclass(frozen=True)
class ObservationTerm:
    frame: str
    quantity: str
    story: int
    dof: str
    coefficient: float = 1.0

    def __post_init__(self) -> None:
        frame = self.frame.lower()
        if frame not in {"relative", "absolute", "ground"}:
            raise ValueError(f"Unsupported observation term frame: {self.frame}")
        if self.story < 0:
            raise ValueError("ObservationTerm.story must be non-negative.")
        coefficient = float(self.coefficient)
        if not np.isfinite(coefficient):
            raise ValueError("ObservationTerm.coefficient must be finite.")
        object.__setattr__(self, "frame", frame)
        object.__setattr__(self, "quantity", _canonical_quantity(self.quantity))
        object.__setattr__(self, "dof", self.dof)
        object.__setattr__(self, "coefficient", coefficient)

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame": self.frame,
            "quantity": self.quantity,
            "story": self.story,
            "dof": self.dof,
            "coefficient": self.coefficient,
        }


@dataclass(frozen=True)
class ObservationOperator:
    terms: tuple[ObservationTerm, ...]
    form: str = "linear_combination"

    def __post_init__(self) -> None:
        if self.form != "linear_combination":
            raise ValueError(f"Unsupported observation operator form: {self.form}")
        if not self.terms:
            raise ValueError("ObservationOperator.terms must not be empty.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "form": self.form,
            "terms": [term.to_dict() for term in self.terms],
        }


@dataclass(frozen=True)
class ObservationChannel:
    observation_id: str
    kind: str
    story: int
    quantity: str
    unit: str
    direction: str | None = None
    dof: str | None = None
    sensor_type: str | None = None
    probe_type: str | None = None
    location: tuple[float, ...] | None = None
    source: dict[str, Any] = field(default_factory=dict)
    operator: ObservationOperator | None = None

    def __post_init__(self) -> None:
        kind = self.kind.lower()
        if kind not in {"physical", "virtual"}:
            raise ValueError(f"Unsupported observation kind: {self.kind}")
        if self.story < 1:
            raise ValueError("ObservationChannel.story must be positive.")
        quantity = _canonical_quantity(self.quantity)
        if self.direction is not None and self.dof is not None:
            raise ValueError("ObservationChannel cannot define both direction and dof.")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "quantity", quantity)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.observation_id,
            "kind": self.kind,
            "story": self.story,
            "quantity": self.quantity,
            "unit": self.unit,
        }
        if self.direction is not None:
            data["direction"] = self.direction
        if self.dof is not None:
            data["dof"] = self.dof
        if self.sensor_type is not None:
            data["sensor_type"] = self.sensor_type
        if self.probe_type is not None:
            data["probe_type"] = self.probe_type
        if self.location is not None:
            data["location"] = list(self.location)
        if self.source:
            data["source"] = self.source
        if self.operator is not None:
            data["operator"] = self.operator.to_dict()
        return data


@dataclass(frozen=True)
class ObservationResult:
    rows: list[dict[str, Any]] = field(default_factory=list)
    channels: tuple[ObservationChannel, ...] = ()
    displacement: tuple[np.ndarray, ...] | None = None
    velocity: tuple[np.ndarray, ...] | None = None
    acceleration: tuple[np.ndarray, ...] | None = None
    absolute_displacement: tuple[np.ndarray, ...] | None = None
    absolute_velocity: tuple[np.ndarray, ...] | None = None
    absolute_acceleration: tuple[np.ndarray, ...] | None = None

    def __post_init__(self) -> None:
        if not self.channels:
            return
        channel_count = len(self.channels)
        for name, histories in (
            ("displacement", self.displacement),
            ("velocity", self.velocity),
            ("acceleration", self.acceleration),
            ("absolute_displacement", self.absolute_displacement),
            ("absolute_velocity", self.absolute_velocity),
            ("absolute_acceleration", self.absolute_acceleration),
        ):
            if histories is not None and len(histories) != channel_count:
                raise ValueError(f"ObservationResult.{name} must have one array per channel.")

    def channels_by_kind(self, kind: str) -> tuple[ObservationChannel, ...]:
        normalized = kind.lower()
        return tuple(channel for channel in self.channels if channel.kind == normalized)

    def rows_by_kind(self, kind: str) -> list[dict[str, Any]]:
        normalized = kind.lower()
        return [row for row in self.rows if row.get("observation_kind") == normalized]


@dataclass(frozen=True)
class SensorResult(ObservationResult):
    """Compatibility alias for legacy sensor mapping results."""


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
    observations: ObservationResult | None = None
    story_stiffness_rows: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        time = np.asarray(self.time, dtype=float)
        if time.ndim != 1:
            raise ValueError("AnalysisResult.time must be one-dimensional.")
        if not np.all(np.isfinite(time)):
            raise ValueError("AnalysisResult.time must be finite.")
        if time.size > 1 and np.any(np.diff(time) <= 0.0):
            raise ValueError("AnalysisResult.time must be strictly increasing.")
        if self.relative.displacement.shape[0] != time.size:
            raise ValueError("Response histories must have one row per time sample.")
        if self.absolute is not None and self.absolute.displacement.shape != self.relative.displacement.shape:
            raise ValueError("AnalysisResult.absolute must match relative response shape.")
        if self.ground is not None and self.ground.displacement.shape[0] != time.size:
            raise ValueError("AnalysisResult.ground must have one row per time sample.")
        mass = np.asarray(self.mass_matrix, dtype=float)
        stiffness = np.asarray(self.stiffness_matrix, dtype=float)
        damping = np.asarray(self.damping_matrix, dtype=float)
        ndof = int(np.prod(self.relative.displacement.shape[1:]))
        if self.modal is not None and self.modal.mode_shapes.shape[0] != ndof:
            raise ValueError("AnalysisResult.modal mode shape row count must match response DOF count.")
        for name, matrix in (
            ("mass_matrix", mass),
            ("stiffness_matrix", stiffness),
            ("damping_matrix", damping),
        ):
            if matrix.shape != (ndof, ndof):
                raise ValueError(f"AnalysisResult.{name} must have shape ({ndof}, {ndof}).")
            if not np.all(np.isfinite(matrix)):
                raise ValueError(f"AnalysisResult.{name} must be finite.")
            if not np.allclose(matrix, matrix.T, rtol=1.0e-8, atol=1.0e-10):
                raise ValueError(f"AnalysisResult.{name} must be symmetric.")
        object.__setattr__(self, "time", time)
        object.__setattr__(self, "mass_matrix", mass)
        object.__setattr__(self, "stiffness_matrix", stiffness)
        object.__setattr__(self, "damping_matrix", damping)
        if self.observations is None and self.sensors is not None:
            object.__setattr__(self, "observations", self.sensors)
        elif self.sensors is None and self.observations is not None:
            object.__setattr__(self, "sensors", _sensor_result_from_observations(self.observations))

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
        if self.observations is not None:
            data["observation_rows"] = self.observations.rows
            data["observation_channels"] = [channel.to_dict() for channel in self.observations.channels]
            data["physical_observation_rows"] = self.observations.rows_by_kind("physical")
            data["virtual_observation_rows"] = self.observations.rows_by_kind("virtual")
        return data


def _put_optional(data: dict[str, Any], key: str, value: Any | None) -> None:
    if value is not None:
        data[key] = value


def _sensor_result_from_observations(observations: ObservationResult) -> SensorResult:
    return SensorResult(
        rows=observations.rows,
        channels=observations.channels,
        displacement=observations.displacement,
        velocity=observations.velocity,
        acceleration=observations.acceleration,
        absolute_displacement=observations.absolute_displacement,
        absolute_velocity=observations.absolute_velocity,
        absolute_acceleration=observations.absolute_acceleration,
    )
