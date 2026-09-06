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
EULER_BEAM_2D = "euler_beam_2d"
RAYLEIGH_BEAM_2D = "rayleigh_beam_2d"
TIMOSHENKO_BEAM_2D = "timoshenko_beam_2d"
SHEAR_FLEXURE_BUILDING_2D = "shear_flexure_building_2d"


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
class BeamSectionConfig:
    story: int
    E: float
    A: float
    I: float
    density: float
    rotational_inertia: float = 0.0
    G: float | None = None
    shear_area: float | None = None


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
class BeamSensorConfig:
    sensor_id: str
    story: int
    dof: str = "U"
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
class GeometryConfig:
    story_heights: tuple[float, ...]
    elevations: tuple[float, ...]
    base_elevation: float = 0.0


@dataclass(frozen=True)
class ModelConfig:
    schema_version: str
    model_type: str
    num_stories: int
    dof_per_floor: tuple[str, ...]
    coordinate_reference: str
    geometry: GeometryConfig
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
    geometry: GeometryConfig
    stories: tuple[ShearStoryConfig, ...]
    sensors: tuple[ShearSensorConfig, ...]
    damping: DampingConfig
    ground_motion: GroundMotionConfig


@dataclass(frozen=True)
class EulerBeamModelConfig:
    schema_version: str
    model_type: str
    num_stories: int
    dof_per_floor: tuple[str, ...]
    geometry: GeometryConfig
    sections: tuple[BeamSectionConfig, ...]
    sensors: tuple[BeamSensorConfig, ...]
    damping: DampingConfig
    ground_motion: GroundMotionConfig


@dataclass(frozen=True)
class RayleighBeamModelConfig:
    schema_version: str
    model_type: str
    num_stories: int
    dof_per_floor: tuple[str, ...]
    geometry: GeometryConfig
    sections: tuple[BeamSectionConfig, ...]
    sensors: tuple[BeamSensorConfig, ...]
    damping: DampingConfig
    ground_motion: GroundMotionConfig


@dataclass(frozen=True)
class TimoshenkoBeamModelConfig:
    schema_version: str
    model_type: str
    num_stories: int
    dof_per_floor: tuple[str, ...]
    geometry: GeometryConfig
    sections: tuple[BeamSectionConfig, ...]
    sensors: tuple[BeamSensorConfig, ...]
    damping: DampingConfig
    ground_motion: GroundMotionConfig


@dataclass(frozen=True)
class ShearFlexureStoryConfig:
    story: int
    flexural_section: BeamSectionConfig
    shear_stiffness: float


@dataclass(frozen=True)
class ShearFlexureModelConfig:
    schema_version: str
    model_type: str
    num_stories: int
    dof_per_floor: tuple[str, ...]
    geometry: GeometryConfig
    stories: tuple[ShearFlexureStoryConfig, ...]
    sensors: tuple[BeamSensorConfig, ...]
    damping: DampingConfig
    ground_motion: GroundMotionConfig


def load_config(path: str | Path) -> ModelConfig:
    """Load a JSON/YAML rigid-floor model config."""

    return normalize_config(_read_mapping(path))


def load_shear_config(path: str | Path) -> ShearModelConfig:
    """Load a JSON/YAML one-direction shear-building model config."""

    return normalize_shear_config(_read_mapping(path))


def load_euler_config(path: str | Path) -> EulerBeamModelConfig:
    """Load a JSON/YAML Euler-Bernoulli beam model config."""

    return normalize_euler_config(_read_mapping(path))


def load_rayleigh_config(path: str | Path) -> RayleighBeamModelConfig:
    """Load a JSON/YAML Rayleigh beam model config."""

    return normalize_rayleigh_config(_read_mapping(path))


def load_timoshenko_config(path: str | Path) -> TimoshenkoBeamModelConfig:
    """Load a JSON/YAML Timoshenko beam model config."""

    return normalize_timoshenko_config(_read_mapping(path))


def load_shear_flexure_config(path: str | Path) -> ShearFlexureModelConfig:
    """Load a JSON/YAML shear-flexure building model config."""

    return normalize_shear_flexure_config(_read_mapping(path))


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
    geometry = normalize_geometry(raw.get("geometry", {}), num_stories)

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
        geometry=geometry,
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
    geometry = normalize_geometry(raw.get("geometry", {}), num_stories)

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
        geometry=geometry,
        stories=stories,
        sensors=sensors,
        damping=damping,
        ground_motion=ground_motion,
    )


def normalize_euler_config(raw: dict[str, Any]) -> EulerBeamModelConfig:
    schema_version = _normalize_schema_version(raw)
    model = raw.get("model", {})
    model_type = _normalize_model_type(model, EULER_BEAM_2D)
    num_stories = int(model.get("num_stories", 10))
    if num_stories <= 0:
        raise ValueError("model.num_stories must be positive.")
    dof_per_floor = _normalize_beam_dof_per_floor(model.get("dof_per_floor", ["U", "Theta"]))
    geometry = normalize_geometry(raw.get("geometry", {}), num_stories)

    defaults = raw.get("section_defaults", {})
    section_rows = raw.get("sections", raw.get("stories", []))
    _validate_story_ids(section_rows, num_stories)
    sections_by_id = {int(item["story"]): item for item in section_rows}
    sections = tuple(
        _normalize_beam_section(i, defaults | sections_by_id.get(i, {}))
        for i in range(1, num_stories + 1)
    )

    story_ids = {section.story for section in sections}
    sensors = tuple(_normalize_beam_sensor(item, story_ids) for item in raw.get("sensors", []))
    _validate_unique_sensor_ids(sensor.sensor_id for sensor in sensors)

    damping = normalize_damping(raw.get("damping", {}), mode_count=2 * num_stories)
    ground_motion = normalize_ground_motion(raw.get("ground_motion", {}))

    return EulerBeamModelConfig(
        schema_version=schema_version,
        model_type=model_type,
        num_stories=num_stories,
        dof_per_floor=dof_per_floor,
        geometry=geometry,
        sections=sections,
        sensors=sensors,
        damping=damping,
        ground_motion=ground_motion,
    )


def normalize_rayleigh_config(raw: dict[str, Any]) -> RayleighBeamModelConfig:
    schema_version = _normalize_schema_version(raw)
    model = raw.get("model", {})
    model_type = _normalize_model_type(model, RAYLEIGH_BEAM_2D)
    num_stories = int(model.get("num_stories", 10))
    if num_stories <= 0:
        raise ValueError("model.num_stories must be positive.")
    dof_per_floor = _normalize_beam_dof_per_floor(model.get("dof_per_floor", ["U", "Theta"]))
    geometry = normalize_geometry(raw.get("geometry", {}), num_stories)

    defaults = raw.get("section_defaults", {})
    section_rows = raw.get("sections", raw.get("stories", []))
    _validate_story_ids(section_rows, num_stories)
    sections_by_id = {int(item["story"]): item for item in section_rows}
    sections = tuple(
        _normalize_beam_section(i, defaults | sections_by_id.get(i, {}), allow_rotational_inertia=True)
        for i in range(1, num_stories + 1)
    )

    story_ids = {section.story for section in sections}
    sensors = tuple(_normalize_beam_sensor(item, story_ids) for item in raw.get("sensors", []))
    _validate_unique_sensor_ids(sensor.sensor_id for sensor in sensors)

    damping = normalize_damping(raw.get("damping", {}), mode_count=2 * num_stories)
    ground_motion = normalize_ground_motion(raw.get("ground_motion", {}))

    return RayleighBeamModelConfig(
        schema_version=schema_version,
        model_type=model_type,
        num_stories=num_stories,
        dof_per_floor=dof_per_floor,
        geometry=geometry,
        sections=sections,
        sensors=sensors,
        damping=damping,
        ground_motion=ground_motion,
    )


def normalize_timoshenko_config(raw: dict[str, Any]) -> TimoshenkoBeamModelConfig:
    schema_version = _normalize_schema_version(raw)
    model = raw.get("model", {})
    model_type = _normalize_model_type(model, TIMOSHENKO_BEAM_2D)
    num_stories = int(model.get("num_stories", 10))
    if num_stories <= 0:
        raise ValueError("model.num_stories must be positive.")
    dof_per_floor = _normalize_beam_dof_per_floor(model.get("dof_per_floor", ["U", "Theta"]))
    geometry = normalize_geometry(raw.get("geometry", {}), num_stories)

    defaults = raw.get("section_defaults", {})
    section_rows = raw.get("sections", raw.get("stories", []))
    _validate_story_ids(section_rows, num_stories)
    sections_by_id = {int(item["story"]): item for item in section_rows}
    sections = tuple(
        _normalize_beam_section(
            i,
            defaults | sections_by_id.get(i, {}),
            allow_rotational_inertia=True,
            require_shear=True,
        )
        for i in range(1, num_stories + 1)
    )

    story_ids = {section.story for section in sections}
    sensors = tuple(_normalize_beam_sensor(item, story_ids) for item in raw.get("sensors", []))
    _validate_unique_sensor_ids(sensor.sensor_id for sensor in sensors)

    damping = normalize_damping(raw.get("damping", {}), mode_count=2 * num_stories)
    ground_motion = normalize_ground_motion(raw.get("ground_motion", {}))

    return TimoshenkoBeamModelConfig(
        schema_version=schema_version,
        model_type=model_type,
        num_stories=num_stories,
        dof_per_floor=dof_per_floor,
        geometry=geometry,
        sections=sections,
        sensors=sensors,
        damping=damping,
        ground_motion=ground_motion,
    )


def normalize_shear_flexure_config(raw: dict[str, Any]) -> ShearFlexureModelConfig:
    schema_version = _normalize_schema_version(raw)
    model = raw.get("model", {})
    model_type = _normalize_model_type(model, SHEAR_FLEXURE_BUILDING_2D)
    num_stories = int(model.get("num_stories", 10))
    if num_stories <= 0:
        raise ValueError("model.num_stories must be positive.")
    dof_per_floor = _normalize_beam_dof_per_floor(model.get("dof_per_floor", ["U", "Theta"]))
    geometry = normalize_geometry(raw.get("geometry", {}), num_stories)

    defaults = raw.get("story_defaults", raw.get("shear_flexure_defaults", {}))
    story_rows = raw.get("stories", raw.get("sections", []))
    _validate_story_ids(story_rows, num_stories)
    stories_by_id = {int(item["story"]): item for item in story_rows}
    stories = tuple(
        _normalize_shear_flexure_story(i, defaults, stories_by_id.get(i, {}), raw.get("section_defaults", {}))
        for i in range(1, num_stories + 1)
    )

    story_ids = {story.story for story in stories}
    sensors = tuple(_normalize_beam_sensor(item, story_ids) for item in raw.get("sensors", []))
    _validate_unique_sensor_ids(sensor.sensor_id for sensor in sensors)

    damping = normalize_damping(raw.get("damping", {}), mode_count=2 * num_stories)
    ground_motion = normalize_ground_motion(raw.get("ground_motion", {}))

    return ShearFlexureModelConfig(
        schema_version=schema_version,
        model_type=model_type,
        num_stories=num_stories,
        dof_per_floor=dof_per_floor,
        geometry=geometry,
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


def normalize_geometry(raw: dict[str, Any], num_stories: int) -> GeometryConfig:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("geometry must be a mapping.")
    base_elevation = _finite_float(raw.get("base_elevation", 0.0), "geometry.base_elevation")
    heights_raw = raw.get("story_heights")
    elevations_raw = raw.get("elevations")

    if heights_raw is None and elevations_raw is None:
        story_heights = tuple(3.0 for _ in range(num_stories))
        elevations = _elevations_from_heights(story_heights, base_elevation)
        return GeometryConfig(
            story_heights=story_heights,
            elevations=elevations,
            base_elevation=base_elevation,
        )

    story_heights: tuple[float, ...] | None = None
    elevations: tuple[float, ...] | None = None
    if heights_raw is not None:
        story_heights = tuple(
            _finite_float(value, f"geometry.story_heights[{index}]")
            for index, value in enumerate(heights_raw)
        )
        _validate_story_heights(story_heights, num_stories)
        elevations = _elevations_from_heights(story_heights, base_elevation)

    if elevations_raw is not None:
        elevations = tuple(
            _finite_float(value, f"geometry.elevations[{index}]")
            for index, value in enumerate(elevations_raw)
        )
        _validate_elevations(elevations, base_elevation, num_stories)
        derived_heights = _heights_from_elevations(elevations, base_elevation)
        if story_heights is not None and not _tuples_allclose(story_heights, derived_heights):
            raise ValueError("geometry.story_heights and geometry.elevations are inconsistent.")
        story_heights = derived_heights

    assert story_heights is not None
    assert elevations is not None
    return GeometryConfig(
        story_heights=story_heights,
        elevations=elevations,
        base_elevation=base_elevation,
    )


def _elevations_from_heights(story_heights: tuple[float, ...], base_elevation: float) -> tuple[float, ...]:
    elevations = []
    current = base_elevation
    for height in story_heights:
        current += height
        elevations.append(current)
    return tuple(elevations)


def _heights_from_elevations(elevations: tuple[float, ...], base_elevation: float) -> tuple[float, ...]:
    heights = []
    previous = base_elevation
    for elevation in elevations:
        heights.append(elevation - previous)
        previous = elevation
    return tuple(heights)


def _validate_story_heights(story_heights: tuple[float, ...], num_stories: int) -> None:
    if len(story_heights) != num_stories:
        raise ValueError("geometry.story_heights length must match model.num_stories.")
    if any(height <= 0.0 for height in story_heights):
        raise ValueError("geometry.story_heights values must be positive.")


def _validate_elevations(elevations: tuple[float, ...], base_elevation: float, num_stories: int) -> None:
    if len(elevations) != num_stories:
        raise ValueError("geometry.elevations length must match model.num_stories.")
    previous = base_elevation
    for elevation in elevations:
        if elevation <= previous:
            raise ValueError("geometry.elevations must be strictly increasing above base_elevation.")
        previous = elevation


def _tuples_allclose(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    if len(a) != len(b):
        return False
    return all(math.isclose(left, right, rel_tol=1.0e-9, abs_tol=1.0e-12) for left, right in zip(a, b))


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


def _normalize_beam_section(
    story_id: int,
    raw: dict[str, Any],
    *,
    allow_rotational_inertia: bool = False,
    require_shear: bool = False,
) -> BeamSectionConfig:
    required = ("E", "A", "I", "density")
    missing = [key for key in required if key not in raw]
    if missing:
        raise ValueError(f"Beam section {story_id} requires {', '.join(missing)}.")
    rotational_inertia = _finite_float(
        raw.get("rotational_inertia", raw.get("J", 0.0)),
        f"Beam section {story_id} rotational_inertia",
    )
    if rotational_inertia < 0.0:
        raise ValueError(f"Beam section {story_id} rotational_inertia must be non-negative.")
    if rotational_inertia > 0.0 and not allow_rotational_inertia:
        raise ValueError("Euler beam sections do not support rotational_inertia; use rayleigh_beam_2d.")
    G = None
    shear_area = None
    if require_shear or raw.get("G") is not None or raw.get("shear_area") is not None or raw.get("Av") is not None:
        if "G" not in raw:
            raise ValueError(f"Beam section {story_id} requires G.")
        shear_area_raw = raw.get("shear_area", raw.get("Av"))
        if shear_area_raw is None:
            raise ValueError(f"Beam section {story_id} requires shear_area.")
        G = _finite_float(raw["G"], f"Beam section {story_id} G")
        shear_area = _finite_float(shear_area_raw, f"Beam section {story_id} shear_area")
        if G <= 0.0 or shear_area <= 0.0:
            raise ValueError(f"Beam section {story_id} G and shear_area must be positive.")
    section = BeamSectionConfig(
        story=story_id,
        E=_finite_float(raw["E"], f"Beam section {story_id} E"),
        A=_finite_float(raw["A"], f"Beam section {story_id} A"),
        I=_finite_float(raw["I"], f"Beam section {story_id} I"),
        density=_finite_float(raw["density"], f"Beam section {story_id} density"),
        rotational_inertia=rotational_inertia,
        G=G,
        shear_area=shear_area,
    )
    if section.E <= 0.0 or section.A <= 0.0 or section.I <= 0.0 or section.density <= 0.0:
        raise ValueError(f"Beam section {story_id} E, A, I, and density must be positive.")
    return section


def _normalize_shear_flexure_story(
    story_id: int,
    defaults: dict[str, Any],
    raw: dict[str, Any],
    section_defaults: dict[str, Any],
) -> ShearFlexureStoryConfig:
    default_flexural = defaults.get("flexural_section", {})
    raw_flexural = raw.get("flexural_section", {})
    inline_flexural = {
        key: raw[key]
        for key in ("E", "A", "I", "density")
        if key in raw
    }
    flexural_section = _normalize_beam_section(
        story_id,
        section_defaults | default_flexural | raw_flexural | inline_flexural,
    )

    shear_stiffness_raw = raw.get("shear_stiffness", defaults.get("shear_stiffness"))
    if shear_stiffness_raw is None:
        raise ValueError(f"Shear-flexure story {story_id} requires shear_stiffness.")
    shear_stiffness = _finite_float(
        shear_stiffness_raw,
        f"Shear-flexure story {story_id} shear_stiffness",
    )
    if shear_stiffness < 0.0:
        raise ValueError(f"Shear-flexure story {story_id} shear_stiffness must be non-negative.")
    return ShearFlexureStoryConfig(
        story=story_id,
        flexural_section=flexural_section,
        shear_stiffness=shear_stiffness,
    )


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


def _normalize_beam_sensor(raw: dict[str, Any], story_ids: set[int]) -> BeamSensorConfig:
    story = int(raw["story"])
    if story not in story_ids:
        raise ValueError(f"Sensor story {story} is outside the model.")
    dof = _normalize_beam_sensor_dof(raw.get("dof", raw.get("direction", "U")))
    quantity = str(raw.get("quantity", "accel")).lower()
    if quantity not in {"disp", "displacement", "vel", "velocity", "accel", "acceleration"}:
        raise ValueError(f"Unsupported sensor quantity: {quantity}")
    return BeamSensorConfig(
        sensor_id=str(raw.get("id", f"sensor_{story}")),
        story=story,
        dof=dof,
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


def _normalize_beam_dof_per_floor(raw: Any) -> tuple[str, ...]:
    dofs = tuple(str(value).strip().lower() for value in raw)
    if dofs != ("u", "theta"):
        raise ValueError("Two-dimensional beam models support dof_per_floor [U, Theta].")
    return ("U", "Theta")


def _normalize_beam_sensor_dof(raw: Any) -> str:
    value = str(raw).strip().lower()
    if value in {"u", "ux", "x"}:
        return "U"
    if value in {"theta", "rotation"}:
        return "Theta"
    if value == "rz":
        raise ValueError("Beam sensor dof Theta is bending rotation, not rigid-floor Rz.")
    raise ValueError(f"Unsupported beam sensor dof: {raw}")


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
    "EULER_BEAM_2D",
    "RAYLEIGH_BEAM_2D",
    "TIMOSHENKO_BEAM_2D",
    "SHEAR_FLEXURE_BUILDING_2D",
    "BeamSectionConfig",
    "BeamSensorConfig",
    "DampingConfig",
    "DirectStiffnessConfig",
    "ElementConfig",
    "GeometryConfig",
    "GroundMotionConfig",
    "ModelConfig",
    "SensorConfig",
    "ShearModelConfig",
    "ShearSensorConfig",
    "ShearFlexureModelConfig",
    "ShearFlexureStoryConfig",
    "ShearStoryConfig",
    "StoryConfig",
    "EulerBeamModelConfig",
    "RayleighBeamModelConfig",
    "TimoshenkoBeamModelConfig",
    "load_config",
    "load_euler_config",
    "load_rayleigh_config",
    "load_shear_flexure_config",
    "load_timoshenko_config",
    "load_shear_config",
    "normalize_config",
    "normalize_damping",
    "normalize_geometry",
    "normalize_ground_motion",
    "normalize_euler_config",
    "normalize_rayleigh_config",
    "normalize_shear_flexure_config",
    "normalize_shear_config",
    "normalize_timoshenko_config",
]
