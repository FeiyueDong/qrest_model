"""Unified backend entry points."""

from __future__ import annotations

from pathlib import Path
import json
from typing import Any, Protocol

from qrest_model.analysis.result import AnalysisResult
from qrest_model.schema import (
    EULER_BEAM_2D,
    RAYLEIGH_BEAM_2D,
    RIGID_FLOOR_SHEAR_3D,
    SHEAR_FLEXURE_BUILDING_2D,
    SHEAR_BUILDING_1D,
    TIMOSHENKO_BEAM_2D,
    EulerBeamModelConfig,
    ModelConfig,
    RayleighBeamModelConfig,
    ShearFlexureModelConfig,
    TimoshenkoBeamModelConfig,
    normalize_euler_config,
    normalize_rayleigh_config,
    normalize_shear_flexure_config,
    normalize_config,
    normalize_timoshenko_config,
)
from qrest_model.schema import ShearModelConfig, normalize_shear_config


ModelCaseInput = (
    ModelConfig
    | ShearModelConfig
    | EulerBeamModelConfig
    | RayleighBeamModelConfig
    | ShearFlexureModelConfig
    | TimoshenkoBeamModelConfig
    | dict[str, Any]
    | str
    | Path
)


class AnalysisBackend(Protocol):
    def run(self, case: ModelCaseInput) -> AnalysisResult:
        ...


class DirectBackend:
    def run(self, case: ModelCaseInput) -> AnalysisResult:
        from qrest_model.backends.direct_euler import run_result as run_euler
        from qrest_model.backends.direct_rayleigh import run_result as run_rayleigh
        from qrest_model.backends.direct_shear import run_result as run_shear
        from qrest_model.backends.direct_shear_flexure import run_result as run_shear_flexure
        from qrest_model.backends.direct_stiffness import run_result as run_rigid_floor
        from qrest_model.backends.direct_timoshenko import run_result as run_timoshenko

        model_type, payload = dispatch_model_case(case)
        if model_type == SHEAR_BUILDING_1D:
            return run_shear(payload)
        if model_type == EULER_BEAM_2D:
            return run_euler(payload)
        if model_type == RAYLEIGH_BEAM_2D:
            return run_rayleigh(payload)
        if model_type == TIMOSHENKO_BEAM_2D:
            return run_timoshenko(payload)
        if model_type == SHEAR_FLEXURE_BUILDING_2D:
            return run_shear_flexure(payload)
        return run_rigid_floor(payload)


class OpenSeesBackend:
    def run(self, case: ModelCaseInput) -> AnalysisResult:
        from qrest_model.backends.opensees_euler import run_result as run_euler
        from qrest_model.backends.opensees_rayleigh import run_result as run_rayleigh
        from qrest_model.backends.opensees_shear import run_result as run_shear
        from qrest_model.backends.opensees_shear_flexure import run_result as run_shear_flexure
        from qrest_model.backends.opensees_story import run_result as run_rigid_floor
        from qrest_model.backends.opensees_timoshenko import run_result as run_timoshenko

        model_type, payload = dispatch_model_case(case)
        if model_type == SHEAR_BUILDING_1D:
            return run_shear(payload)
        if model_type == EULER_BEAM_2D:
            return run_euler(payload)
        if model_type == RAYLEIGH_BEAM_2D:
            return run_rayleigh(payload)
        if model_type == TIMOSHENKO_BEAM_2D:
            return run_timoshenko(payload)
        if model_type == SHEAR_FLEXURE_BUILDING_2D:
            return run_shear_flexure(payload)
        return run_rigid_floor(payload)


def run_analysis(case: ModelCaseInput, *, backend: str = "direct") -> AnalysisResult:
    return backend_by_name(backend).run(case)


def backend_by_name(name: str) -> AnalysisBackend:
    normalized = name.replace("_", "-").lower()
    if normalized == "direct":
        return DirectBackend()
    if normalized in {"opensees", "open-sees"}:
        return OpenSeesBackend()
    raise ValueError(f"Unsupported backend: {name}")


def normalize_model_case(
    case: ModelCaseInput,
) -> (
    ModelConfig
    | ShearModelConfig
    | EulerBeamModelConfig
    | RayleighBeamModelConfig
    | TimoshenkoBeamModelConfig
    | ShearFlexureModelConfig
):
    if isinstance(
        case,
        (
            ModelConfig,
            ShearModelConfig,
            EulerBeamModelConfig,
            RayleighBeamModelConfig,
            TimoshenkoBeamModelConfig,
            ShearFlexureModelConfig,
        ),
    ):
        return case
    raw = _load_raw_case(case) if isinstance(case, (str, Path)) else case
    model_type = _case_model_type(raw)
    if model_type == SHEAR_BUILDING_1D:
        return normalize_shear_config(raw)
    if model_type == RIGID_FLOOR_SHEAR_3D:
        return normalize_config(raw)
    if model_type == EULER_BEAM_2D:
        return normalize_euler_config(raw)
    if model_type == RAYLEIGH_BEAM_2D:
        return normalize_rayleigh_config(raw)
    if model_type == TIMOSHENKO_BEAM_2D:
        return normalize_timoshenko_config(raw)
    if model_type == SHEAR_FLEXURE_BUILDING_2D:
        return normalize_shear_flexure_config(raw)
    raise ValueError(f"Unsupported model.type: {model_type}")


def dispatch_model_case(
    case: ModelCaseInput,
) -> tuple[
    str,
    ModelConfig
    | ShearModelConfig
    | EulerBeamModelConfig
    | RayleighBeamModelConfig
    | TimoshenkoBeamModelConfig
    | ShearFlexureModelConfig
    | str
    | Path,
]:
    if isinstance(case, ShearModelConfig):
        return SHEAR_BUILDING_1D, case
    if isinstance(case, EulerBeamModelConfig):
        return EULER_BEAM_2D, case
    if isinstance(case, RayleighBeamModelConfig):
        return RAYLEIGH_BEAM_2D, case
    if isinstance(case, TimoshenkoBeamModelConfig):
        return TIMOSHENKO_BEAM_2D, case
    if isinstance(case, ShearFlexureModelConfig):
        return SHEAR_FLEXURE_BUILDING_2D, case
    if isinstance(case, ModelConfig):
        return RIGID_FLOOR_SHEAR_3D, case
    if isinstance(case, (str, Path)):
        raw = _load_raw_case(case)
        return _case_model_type(raw), case
    model_type = _case_model_type(case)
    return model_type, normalize_model_case(case)


def _load_raw_case(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    raw_text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "YAML configs require PyYAML. Install pyyaml or use a JSON config."
            ) from exc
        return yaml.safe_load(raw_text)
    return json.loads(raw_text)


def _case_model_type(raw: dict[str, Any]) -> str:
    model = raw.get("model", {})
    model_type = model.get("type")
    if model_type is not None:
        return str(model_type)
    dof_per_floor = tuple(model.get("dof_per_floor", ()))
    if dof_per_floor in {("Ux",), ("Uy",)}:
        return SHEAR_BUILDING_1D
    if dof_per_floor == ("Ux", "Uy", "Rz"):
        return RIGID_FLOOR_SHEAR_3D
    raise ValueError("model.type is required when dof_per_floor cannot identify a legacy model.")
