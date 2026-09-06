"""Canonical scalar-series access for observation histories."""

from __future__ import annotations

from typing import Any

import numpy as np

from qrest_model.analysis.result import ObservationChannel, ObservationResult


def canonical_quantity(quantity: str) -> str:
    normalized = quantity.lower()
    if normalized in {"disp", "displacement"}:
        return "displacement"
    if normalized in {"vel", "velocity"}:
        return "velocity"
    if normalized in {"accel", "acceleration"}:
        return "acceleration"
    raise ValueError(f"Unsupported observation quantity: {quantity}")


def observation_history_name(quantity: str, *, absolute: bool) -> str:
    name = canonical_quantity(quantity)
    return f"absolute_{name}" if absolute else name


def observation_histories(
    observations: ObservationResult,
    quantity: str,
    *,
    kind: str | None = None,
    absolute: bool = True,
) -> tuple[np.ndarray, ...] | None:
    name = canonical_quantity(quantity)
    if absolute:
        absolute_histories = getattr(observations, f"absolute_{name}")
        if absolute_histories is not None:
            return absolute_histories
        if kind == "physical":
            return getattr(observations, name)
    return getattr(observations, name)


def extract_observation_series(
    observations: ObservationResult,
    channel_index: int,
    *,
    quantity: str | None = None,
    absolute: bool = True,
) -> np.ndarray:
    channel = observations.channels[channel_index]
    histories = observation_histories(
        observations,
        quantity or channel.quantity,
        kind=channel.kind,
        absolute=absolute,
    )
    if histories is None:
        raise ValueError(f"Observation {channel.observation_id} has no {quantity or channel.quantity} history.")
    return extract_channel_series(channel, histories[channel_index])


def extract_channel_series(channel: ObservationChannel, history: np.ndarray) -> np.ndarray:
    values = np.asarray(history, dtype=float)
    if values.ndim == 1:
        return values.copy()
    if values.ndim != 2:
        raise ValueError(f"Observation history for {channel.observation_id} must be one- or two-dimensional.")
    return values[:, component_index(channel, values.shape[1])].copy()


def add_to_channel_series(channel: ObservationChannel, history: np.ndarray, delta: np.ndarray) -> np.ndarray:
    values = np.asarray(history, dtype=float).copy()
    delta_values = np.asarray(delta, dtype=float)
    if values.ndim == 1:
        if values.shape != delta_values.shape:
            raise ValueError(f"Noise shape for {channel.observation_id} does not match scalar observation history.")
        return values + delta_values
    if values.ndim != 2:
        raise ValueError(f"Observation history for {channel.observation_id} must be one- or two-dimensional.")
    if values.shape[0] != delta_values.shape[0]:
        raise ValueError(f"Noise length for {channel.observation_id} does not match observation history.")
    values[:, component_index(channel, values.shape[1])] += delta_values
    return values


def refresh_observation_rows(observations: ObservationResult) -> list[dict[str, Any]]:
    if not observations.rows or not observations.channels:
        return list(observations.rows)
    step_count = _step_count(observations)
    if len(observations.rows) != len(observations.channels) * step_count:
        raise ValueError("ObservationResult.rows must be channel-major and match observation history length.")

    rows: list[dict[str, Any]] = []
    for channel_index, channel in enumerate(observations.channels):
        for step in range(step_count):
            row = dict(observations.rows[channel_index * step_count + step])
            _update_component_columns(row, observations, channel_index, step, absolute=False)
            _update_component_columns(row, observations, channel_index, step, absolute=True)
            row["value"] = float(extract_observation_series(observations, channel_index, absolute=True)[step])
            row["relative_value"] = float(extract_observation_series(observations, channel_index, absolute=False)[step])
            rows.append(row)
    return rows


def component_index(channel: ObservationChannel, component_count: int) -> int:
    label = (channel.direction or channel.dof or "").upper()
    if label in {"X", "UX", "U"}:
        return 0
    if label in {"Y", "UY"}:
        if component_count < 2:
            raise ValueError(f"Observation {channel.observation_id} has no Y component.")
        return 1
    if label == "THETA":
        if component_count < 2:
            raise ValueError(f"Observation {channel.observation_id} has no Theta component.")
        return 1
    if label == "RZ":
        if component_count < 3:
            raise ValueError(f"Observation {channel.observation_id} has no RZ component.")
        return 2
    if component_count == 1:
        return 0
    raise ValueError(f"Observation {channel.observation_id} does not define a component label.")


def _step_count(observations: ObservationResult) -> int:
    for histories in (
        observations.displacement,
        observations.velocity,
        observations.acceleration,
        observations.absolute_displacement,
        observations.absolute_velocity,
        observations.absolute_acceleration,
    ):
        if histories:
            return int(np.asarray(histories[0]).shape[0])
    raise ValueError("ObservationResult has rows but no histories.")


def _update_component_columns(
    row: dict[str, Any],
    observations: ObservationResult,
    channel_index: int,
    step: int,
    *,
    absolute: bool,
) -> None:
    for quantity in ("displacement", "velocity", "acceleration"):
        histories = observation_histories(
            observations,
            quantity,
            kind=observations.channels[channel_index].kind,
            absolute=absolute,
        )
        if histories is None:
            continue
        history = np.asarray(histories[channel_index], dtype=float)
        keys = _component_keys(quantity, history[step], absolute=absolute)
        values = np.ravel(history[step])
        for key, value in zip(keys, values):
            if key in row:
                row[key] = float(value)


def _component_keys(quantity: str, value: np.ndarray, *, absolute: bool) -> list[str]:
    size = int(np.ravel(value).size)
    if quantity == "displacement":
        keys = {1: ["u"], 2: ["u", "theta"], 3: ["ux", "uy", "rz"]}.get(size)
    elif quantity == "velocity":
        keys = {1: ["v"], 2: ["v", "vtheta"], 3: ["vx", "vy", "vrz"]}.get(size)
    else:
        keys = {1: ["a"], 2: ["a", "atheta"], 3: ["ax", "ay", "arz"]}.get(size)
    if keys is None:
        raise ValueError(f"Unsupported observation component count: {size}")
    if absolute:
        return [f"abs_{key}" for key in keys]
    return keys


__all__ = [
    "add_to_channel_series",
    "canonical_quantity",
    "component_index",
    "extract_channel_series",
    "extract_observation_series",
    "observation_histories",
    "observation_history_name",
    "refresh_observation_rows",
]
