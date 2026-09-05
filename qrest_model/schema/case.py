"""Configuration schema and normalization for qREST model cases."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
import math
from typing import Any
import warnings


SCHEMA_VERSION = "2.0"
RIGID_FLOOR_SHEAR_3D = "rigid_floor_shear_3d"
SHEAR_BUILDING_1D = "shear_building_1d"


@dataclass(frozen=True)
class ElementConfig:
    element_id: str | None
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
class ShearStoryConfig:
    story: int
    mass: float
    stiffness: float


@dataclass(frozen=True)
class SensorConfig:
    sensor_id: str
    story: int
    x: float
    y: float
    direction: str
    quantity: str = "accel"


@dataclass(frozen=True)
class ShearSensorConfig:
    sensor_id: str
    story: int
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
    schema_version: str
    model_type: str
    num_stories: int
    dof_per_floor: tuple[str, ...]
    coordinate_reference: str
    stories: tuple[StoryConfig, ...]
    sensors: tuple[SensorConfig, ...]
    damping: DampingConfig
    ground_motion: GroundMotionConfig


@dataclass(frozen=True)
class ShearModelConfig:
    schema_version: str
    model_type: str
    num_stories: int
    direction: str
    stories: tuple[ShearStoryConfig, ...]
    sensors: tuple[ShearSensorConfig, ...]
    damping: DampingConfig
    ground_motion: GroundMotionConfig


def load_config(path: str | Path) -> ModelConfig:
    """Load a JSON/YAML rigid-floor model config."""

    return normalize_config(_read_mapping(path))


def load_shear_config(path: str | Path) -> ShearModelConfig:
    """Load a JSON/YAML one-direction shear-building model config."""

    return normalize_shear_config(_read_mapping(path))


def normalize_config(raw: dict[str, Any]) -> ModelConfig:
    schema_version = _normalize_schema_version(raw)
    model = raw.get("model", {})
    model_type = _normalize_model_type(model, RIGID_FLOOR_SHEAR_3D)
    num_stories = int(model.get("num_stories", 10))
    dof_per_floor = tuple(model.get("dof_per_floor", ["Ux", "Uy", "Rz"]))
    coordinate_reference = model.get("coordinate_reference", "geometry_center")
    if dof_per_floor != ("Ux", "Uy", "Rz"):
        raise ValueError("Only three-DOF floors [Ux, Uy, Rz] are supported.")
    if num_stories <= 0:
        raise ValueError("model.num_stories must be positive.")

    defaults = raw.get("floor_defaults", {})
    _validate_story_ids(raw.get("stories", []), num_stories)
    stories_by_id = {int(item["story"]): item for item in raw.get("stories", [])}
    stories = tuple(
        _normalize_rigid_story(
            i,
            defaults | stories_by_id.get(i, {}),
            coordinate_reference,
        )
        for i in range(1, num_stories + 1)
    )

    story_map = {story.story: story for story in stories}
    sensors = tuple(
        _normalize_sensor(item, story_map, coordinate_reference)
        for item in raw.get("sensors", [])
    )
    _validate_unique_sensor_ids(sensor.sensor_id for sensor in sensors)

    damping = normalize_damping(raw.get("damping", {}), mode_count=3 * num_stories)
    ground_motion = normalize_ground_motion(raw.get("ground_motion", {}))

    return ModelConfig(
        schema_version=schema_version,
        model_type=model_type,
        num_stories=num_stories,
        dof_per_floor=dof_per_floor,
        coordinate_reference=coordinate_reference,
        stories=stories,
        sensors=sensors,
        damping=damping,
        ground_motion=ground_motion,
    )


def normalize_shear_config(raw: dict[str, Any]) -> ShearModelConfig:
    schema_version = _normalize_schema_version(raw)
    model = raw.get("model", {})
    model_type = _normalize_model_type(model, SHEAR_BUILDING_1D)
    num_stories = int(model.get("num_stories", 10))
    if num_stories <= 0:
        raise ValueError("model.num_stories must be positive.")
    dof_per_floor = tuple(model.get("dof_per_floor", ["Ux"]))
    if dof_per_floor not in {("Ux",), ("Uy",)}:
        raise ValueError("One-direction shear models support dof_per_floor [Ux] or [Uy].")
    direction = dof_per_floor[0][-1].upper()

    defaults = raw.get("floor_defaults", {})
    _validate_story_ids(raw.get("stories", []), num_stories)
    stories_by_id = {int(item["story"]): item for item in raw.get("stories", [])}
    stories = tuple(
        _normalize_shear_story(i, defaults | stories_by_id.get(i, {}))
        for i in range(1, num_stories + 1)
    )

    story_ids = {story.story for story in stories}
    sensors = tuple(_normalize_shear_sensor(item, story_ids) for item in raw.get("sensors", []))
    _validate_unique_sensor_ids(sensor.sensor_id for sensor in sensors)

    damping = normalize_damping(raw.get("damping", {}), mode_count=num_stories)
    ground_motion = normalize_ground_motion(raw.get("ground_motion", {}))

    return ShearModelConfig(
        schema_version=schema_version,
        model_type=model_type,
        num_stories=num_stories,
        direction=direction,
        stories=stories,
        sensors=sensors,
        damping=damping,
        ground_motion=ground_motion,
    )


def normalize_damping(raw: dict[str, Any], mode_count: int) -> DampingConfig:
    damping_type = str(raw.get("type", "rayleigh")).lower()
    zeta = _finite_float(raw.get("zeta", 0.02), "damping.zeta")
    modes_raw = raw.get("modes", [1, 3])
    modes = tuple(int(v) for v in modes_raw)
    damping = DampingConfig(type=damping_type, zeta=zeta, modes=modes)  # type: ignore[arg-type]
    if damping.type != "rayleigh":
        raise ValueError("Only Rayleigh damping is supported in the first version.")
    if damping.zeta < 0.0:
        raise ValueError("damping.zeta must be non-negative.")
    if len(damping.modes) != 2:
        raise ValueError("damping.modes must contain exactly two mode numbers.")
    if damping.modes[0] == damping.modes[1]:
        raise ValueError("damping.modes must contain two distinct mode numbers.")
    if any(mode < 1 for mode in damping.modes):
        raise ValueError("damping.modes must use one-based positive mode numbers.")
    if max(damping.modes) > mode_count:
        raise ValueError(
            f"damping.modes cannot exceed the model mode count ({mode_count})."
        )
    return damping


def normalize_ground_motion(raw: dict[str, Any]) -> GroundMotionConfig:
    ground_motion = GroundMotionConfig(
        dt=_finite_float(raw.get("dt", 0.01), "ground_motion.dt"),
        duration=_finite_float(raw.get("duration", 20.0), "ground_motion.duration"),
        ax_file=raw.get("ax_file"),
        ay_file=raw.get("ay_file"),
        ax_scale=_finite_float(raw.get("ax_scale", 1.0), "ground_motion.ax_scale"),
        ay_scale=_finite_float(raw.get("ay_scale", 1.0), "ground_motion.ay_scale"),
        synthetic=dict(raw.get("synthetic", {})),
    )
    if ground_motion.dt <= 0.0 or ground_motion.duration <= 0.0:
        raise ValueError("ground_motion.dt and duration must be positive.")
    return ground_motion


def _read_mapping(path: str | Path) -> dict[str, Any]:
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
    if not isinstance(raw, dict):
        raise ValueError(f"Config root must be a mapping: {path}")
    return raw


def _normalize_rigid_story(
    story_id: int,
    raw: dict[str, Any],
    coordinate_reference: str,
) -> StoryConfig:
    if "mass" not in raw or "jz" not in raw:
        raise ValueError(f"Story {story_id} requires mass and jz.")
    mass = _finite_float(raw["mass"], f"Story {story_id} mass")
    jz = _finite_float(raw["jz"], f"Story {story_id} jz")
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
        kx = _finite_float(direct_raw["kx"], f"Story {story_id} direct_stiffness.kx")
        ky = _finite_float(direct_raw["ky"], f"Story {story_id} direct_stiffness.ky")
        ktheta = _finite_float(
            direct_raw["ktheta"],
            f"Story {story_id} direct_stiffness.ktheta",
        )
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
        raise ValueError(f"Story {story_id} requires elements or direct_stiffness.")
    return StoryConfig(
        story=story_id,
        mass=mass,
        jz=jz,
        mass_center=mass_center,
        elements=elements,
        direct_stiffness=direct,
    )


def _normalize_shear_story(story_id: int, raw: dict[str, Any]) -> ShearStoryConfig:
    if "mass" not in raw:
        raise ValueError(f"Story {story_id} requires mass.")
    stiffness = raw.get("stiffness", raw.get("kx", raw.get("ky")))
    if stiffness is None:
        raise ValueError(f"Story {story_id} requires stiffness.")
    mass = _finite_float(raw["mass"], f"Story {story_id} mass")
    stiffness_value = _finite_float(stiffness, f"Story {story_id} stiffness")
    if mass <= 0.0 or stiffness_value <= 0.0:
        raise ValueError(f"Story {story_id} mass and stiffness must be positive.")
    return ShearStoryConfig(story=story_id, mass=mass, stiffness=stiffness_value)


def _normalize_sensor(
    raw: dict[str, Any],
    story_map: dict[int, StoryConfig],
    coordinate_reference: str,
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
        x=_to_centroid(raw.get("x", 0.0), story.mass_center[0], coordinate_reference),
        y=_to_centroid(raw.get("y", 0.0), story.mass_center[1], coordinate_reference),
        direction=direction,
        quantity=quantity,
    )


def _normalize_shear_sensor(raw: dict[str, Any], story_ids: set[int]) -> ShearSensorConfig:
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
    kx = _finite_float(raw.get("kx", 0.0), f"Story {story_id} element kx")
    ky = _finite_float(raw.get("ky", 0.0), f"Story {story_id} element ky")
    if kx <= 0.0 or ky <= 0.0:
        raise ValueError(f"Story {story_id} element stiffness values must be positive.")
    return ElementConfig(
        element_id=str(raw["id"]) if raw.get("id") is not None else None,
        x=_to_centroid(raw.get("x", 0.0), mass_center[0], coordinate_reference),
        y=_to_centroid(raw.get("y", 0.0), mass_center[1], coordinate_reference),
        kx=kx,
        ky=ky,
    )


def _normalize_schema_version(raw: dict[str, Any]) -> str:
    version = raw.get("schema_version")
    if version is None:
        warnings.warn(
            f"Missing schema_version; treating config as legacy compatible with {SCHEMA_VERSION}.",
            UserWarning,
            stacklevel=3,
        )
        return "legacy"
    version = str(version)
    if version != SCHEMA_VERSION:
        raise ValueError(f"Unsupported schema_version {version!r}; expected {SCHEMA_VERSION!r}.")
    return version


def _normalize_model_type(model: dict[str, Any], expected: str) -> str:
    model_type = model.get("type")
    if model_type is None:
        warnings.warn(
            f"Missing model.type; inferring legacy model type {expected}.",
            UserWarning,
            stacklevel=3,
        )
        return expected
    model_type = str(model_type)
    if model_type != expected:
        raise ValueError(f"Unsupported model.type {model_type!r}; expected {expected!r}.")
    return model_type


def _validate_unique_sensor_ids(sensor_ids: Any) -> None:
    seen: set[str] = set()
    for sensor_id in sensor_ids:
        if sensor_id in seen:
            raise ValueError(f"Sensor ID {sensor_id!r} is defined more than once.")
        seen.add(sensor_id)


def _point(value: Any) -> tuple[float, float]:
    if len(value) != 2:
        raise ValueError("Point values must have two components.")
    return _finite_float(value[0], "Point x"), _finite_float(value[1], "Point y")


def _to_centroid(value: Any, mass_center_component: float, reference: str) -> float:
    value = _finite_float(value, "Coordinate value")
    if reference == "geometry_center":
        return value - mass_center_component
    if reference in {"mass_center", "centroid"}:
        return value
    raise ValueError(f"Unsupported coordinate_reference: {reference}")


def _finite_float(value: Any, label: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite.")
    return result


__all__ = [
    "SCHEMA_VERSION",
    "RIGID_FLOOR_SHEAR_3D",
    "SHEAR_BUILDING_1D",
    "DampingConfig",
    "DirectStiffnessConfig",
    "ElementConfig",
    "GroundMotionConfig",
    "ModelConfig",
    "SensorConfig",
    "ShearModelConfig",
    "ShearSensorConfig",
    "ShearStoryConfig",
    "StoryConfig",
    "load_config",
    "load_shear_config",
    "normalize_config",
    "normalize_damping",
    "normalize_ground_motion",
    "normalize_shear_config",
]
