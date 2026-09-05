"""Configuration loading for one-direction shear-building models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from typing import Any

from .config import DampingConfig, GroundMotionConfig


@dataclass(frozen=True)
class ShearStoryConfig:
    story: int
    mass: float
    stiffness: float


@dataclass(frozen=True)
class ShearSensorConfig:
    sensor_id: str
    story: int
    quantity: str = "accel"


@dataclass(frozen=True)
class ShearModelConfig:
    num_stories: int
    direction: str
    stories: tuple[ShearStoryConfig, ...]
    sensors: tuple[ShearSensorConfig, ...]
    damping: DampingConfig
    ground_motion: GroundMotionConfig


def load_shear_config(path: str | Path) -> ShearModelConfig:
    path = Path(path)
    raw_text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "YAML configs require PyYAML. Install pyyaml or use a JSON config."
            ) from exc
        raw = yaml.safe_load(raw_text)
    else:
        raw = json.loads(raw_text)
    return normalize_shear_config(raw)


def normalize_shear_config(raw: dict[str, Any]) -> ShearModelConfig:
    model = raw.get("model", {})
    num_stories = int(model.get("num_stories", 10))
    if num_stories <= 0:
        raise ValueError("model.num_stories must be positive.")
    dof_per_floor = tuple(model.get("dof_per_floor", ["Ux"]))
    if dof_per_floor not in {("Ux",), ("Uy",)}:
        raise ValueError("One-direction shear models support dof_per_floor [Ux] or [Uy].")
    direction = dof_per_floor[0][-1].upper()

    defaults = raw.get("floor_defaults", {})
    stories_by_id = {int(item["story"]): item for item in raw.get("stories", [])}
    stories = tuple(
        _normalize_story(i, defaults | stories_by_id.get(i, {}))
        for i in range(1, num_stories + 1)
    )

    story_ids = {story.story for story in stories}
    sensors = tuple(_normalize_sensor(item, story_ids) for item in raw.get("sensors", []))

    damping_raw = raw.get("damping", {})
    damping = DampingConfig(
        type=str(damping_raw.get("type", "rayleigh")).lower(),
        zeta=float(damping_raw.get("zeta", 0.02)),
        modes=tuple(int(v) for v in damping_raw.get("modes", [1, 3]))[:2],
    )
    if damping.type != "rayleigh":
        raise ValueError("Only Rayleigh damping is supported.")
    if len(damping.modes) != 2:
        raise ValueError("damping.modes must contain two mode numbers.")

    gm_raw = raw.get("ground_motion", {})
    ground_motion = GroundMotionConfig(
        dt=float(gm_raw.get("dt", 0.01)),
        duration=float(gm_raw.get("duration", 20.0)),
        ax_file=gm_raw.get("ax_file"),
        ay_file=gm_raw.get("ay_file"),
        ax_scale=float(gm_raw.get("ax_scale", 1.0)),
        ay_scale=float(gm_raw.get("ay_scale", 1.0)),
        synthetic=dict(gm_raw.get("synthetic", {})),
    )
    if ground_motion.dt <= 0.0 or ground_motion.duration <= 0.0:
        raise ValueError("ground_motion.dt and duration must be positive.")

    return ShearModelConfig(
        num_stories=num_stories,
        direction=direction,
        stories=stories,
        sensors=sensors,
        damping=damping,
        ground_motion=ground_motion,
    )


def _normalize_story(story_id: int, raw: dict[str, Any]) -> ShearStoryConfig:
    if "mass" not in raw:
        raise ValueError(f"Story {story_id} requires mass.")
    stiffness = raw.get("stiffness", raw.get("kx", raw.get("ky")))
    if stiffness is None:
        raise ValueError(f"Story {story_id} requires stiffness.")
    return ShearStoryConfig(
        story=story_id,
        mass=float(raw["mass"]),
        stiffness=float(stiffness),
    )


def _normalize_sensor(raw: dict[str, Any], story_ids: set[int]) -> ShearSensorConfig:
    story = int(raw["story"])
    if story not in story_ids:
        raise ValueError(f"Sensor story {story} is outside the model.")
    quantity = str(raw.get("quantity", "accel")).lower()
    if quantity not in {"disp", "displacement", "vel", "velocity", "accel", "acceleration"}:
        raise ValueError(f"Unsupported sensor quantity: {quantity}")
    return ShearSensorConfig(
        sensor_id=str(raw.get("id", f"sensor_{story}")),
        story=story,
        quantity=quantity,
    )
