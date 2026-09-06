"""Noise model configuration primitives."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NoiseConfig:
    enabled: bool = False
    seed: int | None = None
    noise_type: str = "gaussian_white"
    target: str = "physical"
    level_mode: str = "std_ratio"
    level_value: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "type": self.noise_type if self.enabled else "none",
            "seed": self.seed,
            "target": self.target,
            "level": {
                "mode": self.level_mode,
                "value": self.level_value,
            },
        }


def normalize_noise_config(raw: dict[str, Any] | None) -> NoiseConfig:
    if not raw:
        return NoiseConfig()
    enabled = bool(raw.get("enabled", False))
    model = dict(raw.get("model", {}))
    level = dict(raw.get("level", {}))
    noise_type = str(model.get("type", raw.get("type", "gaussian_white"))).lower()
    target = str(model.get("target", raw.get("target", "physical"))).lower()
    level_mode = str(level.get("mode", raw.get("level_mode", "std_ratio"))).lower()
    level_value = float(level.get("value", raw.get("std_ratio", 0.0)))
    seed_raw = raw.get("seed")
    seed = int(seed_raw) if seed_raw is not None else None
    if not enabled:
        return NoiseConfig(
            enabled=False,
            seed=seed,
            noise_type=noise_type,
            target=target,
            level_mode=level_mode,
            level_value=level_value,
        )
    if seed is None:
        raise ValueError("Research noise requires an explicit seed when enabled.")
    if noise_type != "gaussian_white":
        raise ValueError("Stage 3.5 only supports gaussian_white noise.")
    if target != "physical":
        raise ValueError("Stage 3.5 noise target must be physical.")
    if level_mode != "std_ratio":
        raise ValueError("Stage 3.5 only supports std_ratio noise level.")
    if level_value < 0.0:
        raise ValueError("Noise std_ratio must be non-negative.")
    return NoiseConfig(
        enabled=True,
        seed=seed,
        noise_type=noise_type,
        target=target,
        level_mode=level_mode,
        level_value=level_value,
    )


__all__ = ["NoiseConfig", "normalize_noise_config"]
