"""Shared observation semantics."""

from __future__ import annotations

from qrest_model.analysis.result import ObservationChannel, ObservationOperator, ObservationTerm


PHYSICAL = "physical"
VIRTUAL = "virtual"


def normalize_observation_kind(kind: str | None, *, default: str = PHYSICAL) -> str:
    normalized = (kind or default).lower()
    if normalized not in {PHYSICAL, VIRTUAL}:
        raise ValueError(f"Unsupported observation kind: {kind}")
    return normalized


def quantity_unit(quantity: str, *, axis: str) -> str:
    canonical = _canonical_quantity(quantity)
    if axis == "translation":
        return {"displacement": "m", "velocity": "m/s", "acceleration": "m/s^2"}[canonical]
    if axis == "rotation":
        return {"displacement": "rad", "velocity": "rad/s", "acceleration": "rad/s^2"}[canonical]
    raise ValueError(f"Unsupported observation unit axis: {axis}")


def _canonical_quantity(quantity: str) -> str:
    normalized = quantity.lower()
    if normalized in {"disp", "displacement"}:
        return "displacement"
    if normalized in {"vel", "velocity"}:
        return "velocity"
    if normalized in {"accel", "acceleration"}:
        return "acceleration"
    raise ValueError(f"Unsupported observation quantity: {quantity}")


def physical_channel(
    observation_id: str,
    *,
    story: int,
    quantity: str,
    direction: str,
    location: tuple[float, ...] | None = None,
    source: dict[str, object] | None = None,
    operator: ObservationOperator | None = None,
) -> ObservationChannel:
    return ObservationChannel(
        observation_id=observation_id,
        kind=PHYSICAL,
        story=story,
        quantity=quantity,
        unit=quantity_unit(quantity, axis="translation"),
        direction=direction,
        sensor_type="translation",
        location=location,
        source=source or {},
        operator=operator,
    )


def virtual_dof_probe(
    observation_id: str,
    *,
    story: int,
    quantity: str,
    dof: str,
    source: dict[str, object] | None = None,
    operator: ObservationOperator | None = None,
) -> ObservationChannel:
    axis = "rotation" if dof.upper() in {"RZ", "THETA"} else "translation"
    return ObservationChannel(
        observation_id=observation_id,
        kind=VIRTUAL,
        story=story,
        quantity=quantity,
        unit=quantity_unit(quantity, axis=axis),
        dof=dof,
        probe_type="generalized_dof",
        source=source or {"type": "generalized_dof", "dof": dof},
        operator=operator,
    )


def single_dof_operator(
    *,
    story: int,
    quantity: str,
    dof: str,
    frame: str,
) -> ObservationOperator:
    return ObservationOperator(
        terms=(
            ObservationTerm(
                frame=frame,
                quantity=quantity,
                story=story,
                dof=dof,
                coefficient=1.0,
            ),
        )
    )


def rigid_floor_operator(
    *,
    story: int,
    quantity: str,
    direction: str,
    x: float,
    y: float,
    frame: str,
) -> ObservationOperator:
    normalized = direction.upper()
    if normalized == "X":
        return ObservationOperator(
            terms=(
                ObservationTerm(frame=frame, quantity=quantity, story=story, dof="Ux", coefficient=1.0),
                ObservationTerm(frame=frame, quantity=quantity, story=story, dof="Rz", coefficient=-float(y)),
            )
        )
    if normalized == "Y":
        return ObservationOperator(
            terms=(
                ObservationTerm(frame=frame, quantity=quantity, story=story, dof="Uy", coefficient=1.0),
                ObservationTerm(frame=frame, quantity=quantity, story=story, dof="Rz", coefficient=float(x)),
            )
        )
    if normalized == "RZ":
        return single_dof_operator(story=story, quantity=quantity, dof="Rz", frame=frame)
    raise ValueError(f"Unsupported rigid-floor observation direction: {direction}")


__all__ = [
    "PHYSICAL",
    "VIRTUAL",
    "normalize_observation_kind",
    "physical_channel",
    "quantity_unit",
    "rigid_floor_operator",
    "single_dof_operator",
    "virtual_dof_probe",
]
