"""Derived structural quantity exporters for research datasets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from qrest_model.analysis.result import AnalysisResult
from qrest_model.common.io import ensure_output_dir
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


def write_derived_quantities(output_dir: str | Path, result: AnalysisResult, config: dict[str, Any]) -> dict[str, Any]:
    output = ensure_output_dir(output_dir)
    quantities = derived_structural_quantities(result, config)
    arrays = {"time": result.time}
    arrays.update({quantity["id"]: quantity["values"] for quantity in quantities})
    np.savez_compressed(output / "structural.npz", **arrays)

    metadata = {
        "quantity_count": len(quantities),
        "files": {"structural": "structural.npz"},
        "quantities": [
            {
                "id": quantity["id"],
                "unit": quantity["unit"],
                "shape": list(quantity["values"].shape),
                "source": quantity["source"],
                "description": quantity["description"],
            }
            for quantity in quantities
        ],
    }
    return metadata


def derived_structural_quantities(result: AnalysisResult, config: dict[str, Any]) -> list[dict[str, Any]]:
    model = config.get("model", {})
    model_type = str(model.get("type", result.metadata.extras.get("model_type", "")))
    heights = _story_heights(config, result.relative.displacement.shape[1])
    displacement = result.relative.displacement
    if model_type == SHEAR_BUILDING_1D:
        direction = str(result.metadata.extras.get("direction", model.get("dof_per_floor", ["Ux"])[0][-1])).lower()
        return _translation_derived(displacement, heights, dof=direction)
    if model_type == RIGID_FLOOR_SHEAR_3D:
        return [
            *_translation_derived(displacement[:, :, 0], heights, dof="x"),
            *_translation_derived(displacement[:, :, 1], heights, dof="y"),
        ]
    if model_type in BEAM_LIKE_MODELS:
        return [
            *_translation_derived(displacement[:, :, 0], heights, dof="u"),
            _rotation_difference(displacement[:, :, 1]),
        ]
    raise ValueError(f"Unsupported derived-quantity model type: {model_type}")


def _translation_derived(displacement: np.ndarray, heights: np.ndarray, *, dof: str) -> list[dict[str, Any]]:
    inter_story = _inter_story_difference(displacement)
    drift_ratio = inter_story / heights[None, :]
    return [
        {
            "id": f"inter_story_displacement_{dof}",
            "unit": "m",
            "values": inter_story,
            "source": {
                "type": "relative_displacement_difference",
                "dof": dof,
                "lower_story_base_value": 0.0,
            },
            "description": f"Relative inter-story displacement difference for {dof}.",
        },
        {
            "id": f"inter_story_drift_ratio_{dof}",
            "unit": "1",
            "values": drift_ratio,
            "source": {
                "type": "relative_displacement_difference_divided_by_story_height",
                "dof": dof,
                "height_source": "geometry.story_heights",
            },
            "description": f"Inter-story drift ratio for {dof}.",
        },
    ]


def _rotation_difference(theta: np.ndarray) -> dict[str, Any]:
    return {
        "id": "story_rotation_difference",
        "unit": "rad",
        "values": _inter_story_difference(theta),
        "source": {
            "type": "relative_rotation_difference",
            "dof": "theta",
            "lower_story_base_value": 0.0,
        },
        "description": "Difference of generalized bending rotation between adjacent stories.",
    }


def _inter_story_difference(values: np.ndarray) -> np.ndarray:
    base = np.zeros((values.shape[0], 1), dtype=float)
    lower = np.concatenate([base, values[:, :-1]], axis=1)
    return values - lower


def _story_heights(config: dict[str, Any], num_stories: int) -> np.ndarray:
    geometry = config.get("geometry", {})
    heights = geometry.get("story_heights")
    if heights is None:
        heights = [3.0] * num_stories
    values = np.asarray(heights, dtype=float)
    if values.shape != (num_stories,):
        raise ValueError("geometry.story_heights length must match model.num_stories for derived quantities.")
    if not np.all(np.isfinite(values)) or np.any(values <= 0.0):
        raise ValueError("geometry.story_heights must be finite and positive for derived quantities.")
    return values


__all__ = ["derived_structural_quantities", "write_derived_quantities"]
