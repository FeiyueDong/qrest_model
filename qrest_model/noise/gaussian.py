"""Gaussian white measurement noise for observations."""

from __future__ import annotations

from typing import Any

import numpy as np

from qrest_model.analysis.result import ObservationResult, SensorResult
from qrest_model.noise.config import NoiseConfig, normalize_noise_config
from qrest_model.observations.series import (
    add_to_channel_series,
    extract_channel_series,
    observation_history_name,
    refresh_observation_rows,
)


def apply_observation_noise(
    observations: ObservationResult,
    noise_config: dict[str, Any] | NoiseConfig | None,
) -> tuple[ObservationResult, dict[str, Any]]:
    config = noise_config if isinstance(noise_config, NoiseConfig) else normalize_noise_config(noise_config)
    if not config.enabled:
        return observations, {"enabled": False, **config.to_dict(), "channels": []}

    rng = np.random.default_rng(config.seed)
    histories = {
        "displacement": _copy_histories(observations.displacement),
        "velocity": _copy_histories(observations.velocity),
        "acceleration": _copy_histories(observations.acceleration),
        "absolute_displacement": _copy_histories(observations.absolute_displacement),
        "absolute_velocity": _copy_histories(observations.absolute_velocity),
        "absolute_acceleration": _copy_histories(observations.absolute_acceleration),
    }
    channel_metadata: list[dict[str, Any]] = []
    for index, channel in enumerate(observations.channels):
        if channel.kind != "physical":
            continue
        history_name = observation_history_name(channel.quantity, absolute=True)
        if histories[history_name] is None:
            raise ValueError(f"Observation {channel.observation_id} has no absolute {channel.quantity} history.")
        clean = extract_channel_series(channel, histories[history_name][index])
        signal_std = float(np.std(clean))
        target_std = float(config.level_value * signal_std)
        noise = rng.normal(0.0, target_std, size=clean.shape) if target_std > 0.0 else np.zeros_like(clean)
        histories[history_name][index] = add_to_channel_series(channel, histories[history_name][index], noise)
        relative_name = observation_history_name(channel.quantity, absolute=False)
        if histories[relative_name] is not None:
            histories[relative_name][index] = add_to_channel_series(channel, histories[relative_name][index], noise)
        channel_metadata.append(
            {
                "id": channel.observation_id,
                "kind": channel.kind,
                "quantity": channel.quantity,
                "signal_std": signal_std,
                "target_noise_std": target_std,
                "realized_noise_std": float(np.std(noise)),
            }
        )

    noisy_without_rows = SensorResult(
        rows=observations.rows,
        channels=observations.channels,
        displacement=_tuple_or_none(histories["displacement"]),
        velocity=_tuple_or_none(histories["velocity"]),
        acceleration=_tuple_or_none(histories["acceleration"]),
        absolute_displacement=_tuple_or_none(histories["absolute_displacement"]),
        absolute_velocity=_tuple_or_none(histories["absolute_velocity"]),
        absolute_acceleration=_tuple_or_none(histories["absolute_acceleration"]),
    )
    noisy = SensorResult(
        rows=refresh_observation_rows(noisy_without_rows),
        channels=noisy_without_rows.channels,
        displacement=noisy_without_rows.displacement,
        velocity=noisy_without_rows.velocity,
        acceleration=noisy_without_rows.acceleration,
        absolute_displacement=noisy_without_rows.absolute_displacement,
        absolute_velocity=noisy_without_rows.absolute_velocity,
        absolute_acceleration=noisy_without_rows.absolute_acceleration,
    )
    metadata = config.to_dict() | {"channels": channel_metadata}
    return noisy, metadata


def _copy_histories(histories: tuple[np.ndarray, ...] | None) -> list[np.ndarray] | None:
    if histories is None:
        return None
    return [np.asarray(history, dtype=float).copy() for history in histories]


def _tuple_or_none(histories: list[np.ndarray] | None) -> tuple[np.ndarray, ...] | None:
    if histories is None:
        return None
    return tuple(histories)


__all__ = ["apply_observation_noise"]
