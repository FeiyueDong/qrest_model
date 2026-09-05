"""Configuration loading and normalization for qREST model cases."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
from typing import Any


@dataclass(frozen=True)
class ElementConfig:
    x: float
    y: float
    kx: float
    ky: float


@dataclass(frozen=True)
class DirectStiffnessConfig:
    kx: float
    ky: float
    ktheta: float
    stiffness_center: tuple[float, float] = (0.0, 0.0)


@dataclass(frozen=True)
class StoryConfig:
    story: int
    mass: float
    jz: float
    mass_center: tuple[float, float]
    elements: tuple[ElementConfig, ...] = ()
    direct_stiffness: DirectStiffnessConfig | None = None


@dataclass(frozen=True)
class SensorConfig:
    sensor_id: str
    story: int
    x: float
    y: float
    direction: str
    quantity: str = "accel"


@dataclass(frozen=True)
class DampingConfig:
    type: str = "rayleigh"
    zeta: float = 0.02
    modes: tuple[int, int] = (1, 3)


@dataclass(frozen=True)
class GroundMotionConfig:
    dt: float = 0.01
    duration: float = 20.0
    ax_file: str | None = None
    ay_file: str | None = None
    ax_scale: float = 1.0
    ay_scale: float = 1.0
    synthetic: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelConfig:
    num_stories: int
    dof_per_floor: tuple[str, ...]
    coordinate_reference: str
    stories: tuple[StoryConfig, ...]
    sensors: tuple[SensorConfig, ...]
    damping: DampingConfig
    ground_motion: GroundMotionConfig


def load_config(path: str | Path) -> ModelConfig:
    """Load a JSON/YAML config file and return a normalized model config."""

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
    return normalize_config(raw)


def normalize_config(raw: dict[str, Any]) -> ModelConfig:
    model = raw.get("model", {})
    num_stories = int(model.get("num_stories", 10))
    dof_per_floor = tuple(model.get("dof_per_floor", ["Ux", "Uy", "Rz"]))
    coordinate_reference = model.get("coordinate_reference", "geometry_center")
    if dof_per_floor != ("Ux", "Uy", "Rz"):
        raise ValueError("Only three-DOF floors [Ux, Uy, Rz] are supported.")
    if num_stories <= 0:
        raise ValueError("model.num_stories must be positive.")

    defaults = raw.get("floor_defaults", {})
    _validate_story_ids(raw.get("stories", []), num_stories)
    stories_by_id = {
        int(item["story"]): item for item in raw.get("stories", [])}
    stories = tuple(
        _normalize_story(i, defaults | stories_by_id.get(
            i, {}), coordinate_reference)
        for i in range(1, num_stories + 1)
    )

    story_map = {story.story: story for story in stories}
    sensors = tuple(_normalize_sensor(item, story_map, coordinate_reference) for item in raw.get("sensors", []))

    damping_raw = raw.get("damping", {})
    damping = DampingConfig(
        type=str(damping_raw.get("type", "rayleigh")).lower(),
        zeta=float(damping_raw.get("zeta", 0.02)),
        modes=tuple(int(v) for v in damping_raw.get(
            "modes", [1, 3]))[:2],  # type: ignore
    )
    if damping.type != "rayleigh":
        raise ValueError(
            "Only Rayleigh damping is supported in the first version.")
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

    return ModelConfig(
        num_stories=num_stories,
        dof_per_floor=dof_per_floor,
        coordinate_reference=coordinate_reference,
        stories=stories,
        sensors=sensors,
        damping=damping,
        ground_motion=ground_motion,
    )


def _normalize_story(
    story_id: int, raw: dict[str, Any], coordinate_reference: str
) -> StoryConfig:
    if "mass" not in raw or "jz" not in raw:
        raise ValueError(f"Story {story_id} requires mass and jz.")
    mass = float(raw["mass"])
    jz = float(raw["jz"])
    if mass <= 0.0 or jz <= 0.0:
        raise ValueError(f"Story {story_id} mass and jz must be positive.")
    mass_center = _point(raw.get("mass_center", [0.0, 0.0]))
    elements = tuple(
        _normalize_element(item, mass_center, coordinate_reference, story_id)
        for item in raw.get("elements", [])
    )
    direct = None
    if raw.get("direct_stiffness") is not None:
        direct_raw = raw["direct_stiffness"]
        center = _point(direct_raw.get("stiffness_center", [0.0, 0.0]))
        kx = float(direct_raw["kx"])
        ky = float(direct_raw["ky"])
        ktheta = float(direct_raw["ktheta"])
        if kx <= 0.0 or ky <= 0.0 or ktheta <= 0.0:
            raise ValueError(f"Story {story_id} direct_stiffness values must be positive.")
        direct = DirectStiffnessConfig(
            kx=kx,
            ky=ky,
            ktheta=ktheta,
            stiffness_center=(
                _to_centroid(center[0], mass_center[0], coordinate_reference),
                _to_centroid(center[1], mass_center[1], coordinate_reference),
            ),
        )
    if not elements and direct is None:
        raise ValueError(
            f"Story {story_id} requires elements or direct_stiffness.")
    return StoryConfig(
        story=story_id,
        mass=mass,
        jz=jz,
        mass_center=mass_center,
        elements=elements,
        direct_stiffness=direct,
    )


def _normalize_sensor(
    raw: dict[str, Any], story_map: dict[int, StoryConfig], coordinate_reference: str
) -> SensorConfig:
    story_id = int(raw["story"])
    if story_id not in story_map:
        raise ValueError(f"Sensor story {story_id} is outside the model.")
    story = story_map[story_id]
    direction = str(raw.get("direction", "X")).upper()
    if direction not in {"X", "Y", "RZ"}:
        raise ValueError(f"Unsupported sensor direction: {direction}")
    quantity = str(raw.get("quantity", "accel")).lower()
    if quantity not in {"disp", "displacement", "vel", "velocity", "accel", "acceleration"}:
        raise ValueError(f"Unsupported sensor quantity: {quantity}")
    return SensorConfig(
        sensor_id=str(raw.get("id", f"sensor_{story.story}")),
        story=story.story,
        x=_to_centroid(raw.get("x", 0.0),
                       story.mass_center[0], coordinate_reference),
        y=_to_centroid(raw.get("y", 0.0),
                       story.mass_center[1], coordinate_reference),
        direction=direction,
        quantity=quantity,
    )


def _validate_story_ids(raw_stories: list[dict[str, Any]], num_stories: int) -> None:
    seen: set[int] = set()
    for item in raw_stories:
        story_id = int(item["story"])
        if story_id < 1 or story_id > num_stories:
            raise ValueError(f"Story {story_id} is outside the model.")
        if story_id in seen:
            raise ValueError(f"Story {story_id} is defined more than once.")
        seen.add(story_id)


def _normalize_element(
    raw: dict[str, Any],
    mass_center: tuple[float, float],
    coordinate_reference: str,
    story_id: int,
) -> ElementConfig:
    kx = float(raw.get("kx", 0.0))
    ky = float(raw.get("ky", 0.0))
    if kx <= 0.0 or ky <= 0.0:
        raise ValueError(f"Story {story_id} element stiffness values must be positive.")
    return ElementConfig(
        x=_to_centroid(raw.get("x", 0.0), mass_center[0], coordinate_reference),
        y=_to_centroid(raw.get("y", 0.0), mass_center[1], coordinate_reference),
        kx=kx,
        ky=ky,
    )


def _point(value: Any) -> tuple[float, float]:
    if len(value) != 2:
        raise ValueError("Point values must have two components.")
    return float(value[0]), float(value[1])


def _to_centroid(value: Any, mass_center_component: float, reference: str) -> float:
    value = float(value)
    if reference == "geometry_center":
        return value - mass_center_component
    if reference in {"mass_center", "centroid"}:
        return value
    raise ValueError(f"Unsupported coordinate_reference: {reference}")
