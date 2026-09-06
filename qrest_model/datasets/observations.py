"""Research observation layout expansion helpers."""

from __future__ import annotations

import copy
from typing import Any

from qrest_model.schema import (
    EULER_BEAM_2D,
    RAYLEIGH_BEAM_2D,
    RIGID_FLOOR_SHEAR_3D,
    SHEAR_FLEXURE_BUILDING_2D,
    SHEAR_BUILDING_1D,
    TIMOSHENKO_BEAM_2D,
)

BEAM_LIKE_MODELS = {
    EULER_BEAM_2D,
    RAYLEIGH_BEAM_2D,
    TIMOSHENKO_BEAM_2D,
    SHEAR_FLEXURE_BUILDING_2D,
}


def apply_observation_config(
    model_config: dict[str, Any],
    observation_config: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a runtime config whose sensors are derived from observations.

    Research cases use the top-level ``observations`` object as the semantic
    source of truth. Backends still consume the legacy ``sensors`` field, so
    this adapter expands observations into that compatibility shape.
    """

    if not observation_config:
        return copy.deepcopy(model_config)
    config = copy.deepcopy(model_config)
    config["sensors"] = observation_sensors(config, observation_config)
    return config


def observation_sensors(
    model_config: dict[str, Any],
    observation_config: dict[str, Any],
) -> list[dict[str, Any]]:
    model = model_config.get("model", {})
    model_type = str(model.get("type", ""))
    num_stories = int(model.get("num_stories", 0))
    if num_stories <= 0:
        raise ValueError("model.num_stories must be positive before expanding observations.")
    if model_type == SHEAR_BUILDING_1D:
        sensors = _shear_observation_sensors(model_config, observation_config, num_stories)
    elif model_type in BEAM_LIKE_MODELS:
        sensors = _beam_observation_sensors(observation_config, num_stories)
    elif model_type == RIGID_FLOOR_SHEAR_3D:
        sensors = _rigid_observation_sensors(observation_config, num_stories)
    else:
        raise ValueError(f"Unsupported research observation model.type: {model_type}")
    _validate_unique_ids(sensors)
    return sensors


def _shear_observation_sensors(
    model_config: dict[str, Any],
    observation_config: dict[str, Any],
    num_stories: int,
) -> list[dict[str, Any]]:
    model = model_config.get("model", {})
    direction = str(model.get("dof_per_floor", ["Ux"])[0])[-1].upper()
    sensors: list[dict[str, Any]] = []
    for spec in _observation_specs(observation_config.get("physical"), kind="physical"):
        for story in _stories(spec, num_stories):
            for requested in _axis_values(spec, "directions", default=(direction,)):
                if requested.upper() != direction:
                    raise ValueError(f"Shear observation direction {requested!r} does not match model direction {direction}.")
                sensors.append(
                    {
                        "id": _observation_id(spec, story, direction.lower()),
                        "story": story,
                        "quantity": _quantity(spec),
                        "kind": "physical",
                    }
                )
    for spec in _observation_specs(observation_config.get("virtual"), kind="virtual"):
        for story in _stories(spec, num_stories):
            for dof in _axis_values(spec, "dofs", default=("U",)):
                if dof.upper() not in {"U", f"U{direction}".upper(), direction}:
                    raise ValueError(f"Unsupported shear virtual probe dof: {dof}")
                sensors.append(
                    {
                        "id": _observation_id(spec, story, "u"),
                        "story": story,
                        "quantity": _quantity(spec),
                        "kind": "virtual",
                    }
                )
    return sensors


def _beam_observation_sensors(observation_config: dict[str, Any], num_stories: int) -> list[dict[str, Any]]:
    sensors: list[dict[str, Any]] = []
    for kind in ("physical", "virtual"):
        for spec in _observation_specs(observation_config.get(kind), kind=kind):
            for story in _stories(spec, num_stories):
                for dof in _axis_values(spec, "dofs", default=("U",)):
                    normalized = _beam_dof(dof)
                    sensors.append(
                        {
                            "id": _observation_id(spec, story, normalized.lower()),
                            "story": story,
                            "dof": normalized,
                            "quantity": _quantity(spec),
                            "kind": kind,
                        }
                    )
    return sensors


def _rigid_observation_sensors(observation_config: dict[str, Any], num_stories: int) -> list[dict[str, Any]]:
    sensors: list[dict[str, Any]] = []
    for spec in _observation_specs(observation_config.get("physical"), kind="physical"):
        for story in _stories(spec, num_stories):
            for direction in _axis_values(spec, "directions", default=("X",)):
                normalized = str(direction).upper()
                if normalized not in {"X", "Y"}:
                    raise ValueError(f"Rigid-floor physical observations support X/Y translation only, got {direction!r}.")
                sensors.append(
                    {
                        "id": _observation_id(spec, story, normalized.lower()),
                        "story": story,
                        "x": float(spec.get("x", 0.0)),
                        "y": float(spec.get("y", 0.0)),
                        "direction": normalized,
                        "quantity": _quantity(spec),
                        "kind": "physical",
                    }
                )
    for spec in _observation_specs(observation_config.get("virtual"), kind="virtual"):
        for story in _stories(spec, num_stories):
            for dof in _axis_values(spec, "dofs", default=("Rz",)):
                normalized = str(dof).upper()
                if normalized not in {"RZ"}:
                    raise ValueError(f"Unsupported rigid-floor virtual probe dof: {dof}")
                sensors.append(
                    {
                        "id": _observation_id(spec, story, "rz"),
                        "story": story,
                        "x": float(spec.get("x", 0.0)),
                        "y": float(spec.get("y", 0.0)),
                        "direction": "RZ",
                        "quantity": _quantity(spec),
                        "kind": "virtual",
                    }
                )
    return sensors


def _observation_specs(raw: Any, *, kind: str) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [dict(item, kind=kind) for item in raw]
    if isinstance(raw, dict):
        return [dict(raw, kind=kind)]
    raise ValueError(f"observations.{kind} must be an object or a list of objects.")


def _stories(spec: dict[str, Any], num_stories: int) -> list[int]:
    raw = spec.get("stories", spec.get("story"))
    if raw is None:
        raise ValueError("Observation config requires story or stories.")
    values = raw if isinstance(raw, list) else [raw]
    stories = [int(value) for value in values]
    for story in stories:
        if story < 1 or story > num_stories:
            raise ValueError(f"Observation story {story} is outside the model.")
    return stories


def _axis_values(spec: dict[str, Any], key: str, *, default: tuple[str, ...]) -> list[str]:
    raw = spec.get(key)
    if raw is None and key == "dofs":
        raw = spec.get("directions")
    if raw is None and key == "directions":
        raw = spec.get("dofs")
    if raw is None:
        return list(default)
    return [str(value) for value in (raw if isinstance(raw, list) else [raw])]


def _quantity(spec: dict[str, Any]) -> str:
    return str(spec.get("quantity", "acceleration")).lower()


def _observation_id(spec: dict[str, Any], story: int, suffix: str) -> str:
    if "id" in spec and "stories" not in spec:
        return str(spec["id"])
    return str(spec.get("id_template", f"{story:02d}f_{suffix}")).format(story=story, suffix=suffix)


def _beam_dof(raw: Any) -> str:
    value = str(raw).strip().lower()
    if value in {"u", "ux", "x"}:
        return "U"
    if value in {"theta", "rotation"}:
        return "Theta"
    raise ValueError(f"Unsupported beam observation dof: {raw}")


def _validate_unique_ids(sensors: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for sensor in sensors:
        sensor_id = str(sensor["id"])
        if sensor_id in seen:
            raise ValueError(f"Observation ID {sensor_id!r} is defined more than once.")
        seen.add(sensor_id)


__all__ = ["apply_observation_config", "observation_sensors"]
