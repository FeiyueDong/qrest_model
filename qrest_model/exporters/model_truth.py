"""Model truth exporters for research datasets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from qrest_model.analysis.result import AnalysisResult
from qrest_model.common.io import ensure_output_dir


def write_model_truth(output_dir: str | Path, result: AnalysisResult, config: dict[str, Any]) -> dict[str, Any]:
    output = ensure_output_dir(output_dir)
    dof_labels = truth_dof_labels(config, result)
    _write_response_npz(output / "response.npz", result)
    _write_matrices_npz(output / "matrices.npz", result, dof_labels)
    _write_modal_npz(output / "modal.npz", result, dof_labels)
    summary = _truth_summary(result, config, dof_labels)
    (output / "structural_properties.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return summary


def truth_dof_labels(config: dict[str, Any], result: AnalysisResult) -> list[str]:
    model = config.get("model", {})
    model_type = str(model.get("type", result.metadata.extras.get("model_type", "")))
    num_stories = int(model.get("num_stories", result.relative.displacement.shape[1]))
    if model_type == "shear_building_1d":
        direction = str(result.metadata.extras.get("direction", model.get("dof_per_floor", ["Ux"])[0][-1])).lower()
        return [f"story_{story:02d}_{direction}" for story in range(1, num_stories + 1)]
    if model_type in {
        "euler_beam_2d",
        "rayleigh_beam_2d",
        "timoshenko_beam_2d",
        "shear_flexure_building_2d",
    }:
        return [
            f"story_{story:02d}_{component}"
            for story in range(1, num_stories + 1)
            for component in ("u", "theta")
        ]
    return [
        f"story_{story:02d}_{component}"
        for story in range(1, num_stories + 1)
        for component in ("x", "y", "rz")
    ]


def _write_response_npz(path: Path, result: AnalysisResult) -> None:
    arrays = {
        "time": result.time,
        "relative_displacement": result.relative.displacement,
        "relative_velocity": result.relative.velocity,
        "relative_acceleration": result.relative.acceleration,
    }
    if result.absolute is not None:
        arrays.update(
            {
                "absolute_displacement": result.absolute.displacement,
                "absolute_velocity": result.absolute.velocity,
                "absolute_acceleration": result.absolute.acceleration,
            }
        )
    if result.ground is not None:
        arrays.update(
            {
                "ground_displacement": result.ground.displacement,
                "ground_velocity": result.ground.velocity,
                "ground_acceleration": result.ground.acceleration,
            }
        )
    np.savez_compressed(path, **arrays)


def _write_matrices_npz(path: Path, result: AnalysisResult, dof_labels: list[str]) -> None:
    np.savez_compressed(
        path,
        mass_matrix=result.mass_matrix,
        stiffness_matrix=result.stiffness_matrix,
        damping_matrix=result.damping_matrix,
        dof_labels=np.asarray(dof_labels),
    )


def _write_modal_npz(path: Path, result: AnalysisResult, dof_labels: list[str]) -> None:
    arrays: dict[str, np.ndarray] = {"dof_labels": np.asarray(dof_labels)}
    if result.modal is not None:
        arrays.update(
            {
                "omega": result.modal.omega,
                "frequency_hz": result.modal.frequency,
                "period_s": result.modal.period,
                "mode_shapes": result.modal.mode_shapes,
            }
        )
    np.savez_compressed(path, **arrays)


def _truth_summary(result: AnalysisResult, config: dict[str, Any], dof_labels: list[str]) -> dict[str, Any]:
    metadata = result.metadata.to_dict()
    return {
        "model_type": str(config.get("model", {}).get("type", metadata.get("model_type", ""))),
        "backend": result.metadata.backend,
        "time_steps": int(result.time.size),
        "response_shape": list(result.relative.displacement.shape),
        "dof_count": int(result.mass_matrix.shape[0]),
        "dof_labels": dof_labels,
        "dof_units": truth_dof_units(dof_labels),
        "modal_metadata": {
            "mode_shape_normalization": "mass_normalized",
            "mode_shape_normalization_equation": "phi.T @ M @ phi = I",
            "mode_shape_sign_convention": "largest_abs_component_positive",
            "dof_units": truth_dof_units(dof_labels),
        },
        "matrix_source": metadata.get("matrix_source"),
        "modal_source": metadata.get("modal_source"),
        "response_source": metadata.get("response_source"),
        "backend_modal_source": metadata.get("backend_modal_source"),
        "files": {
            "response": "response.npz",
            "matrices": "matrices.npz",
            "modal": "modal.npz",
        },
    }


def truth_dof_units(dof_labels: list[str]) -> dict[str, str]:
    return {label: _dof_unit(label) for label in dof_labels}


def _dof_unit(label: str) -> str:
    component = label.rsplit("_", 1)[-1].lower()
    if component in {"theta", "rz"}:
        return "rad"
    return "m"


__all__ = ["truth_dof_labels", "truth_dof_units", "write_model_truth"]
