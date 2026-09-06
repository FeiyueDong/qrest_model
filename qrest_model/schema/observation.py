"""Observation schema primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ObservationConfig:
    observation_id: str
    story: int
    kind: str
    quantity: str


@dataclass(frozen=True)
class PhysicalObservationConfig(ObservationConfig):
    sensor_type: str = "translation"
    direction: str = "X"
    location: tuple[float, float] | None = None
    source: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VirtualProbeConfig(ObservationConfig):
    probe_type: str = "generalized_dof"
    dof: str = "U"
    source: dict[str, Any] = field(default_factory=dict)


__all__ = ["ObservationConfig", "PhysicalObservationConfig", "VirtualProbeConfig"]
