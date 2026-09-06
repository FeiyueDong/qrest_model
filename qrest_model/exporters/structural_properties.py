"""Structural property exporters for generated datasets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from qrest_model.analysis.result import AnalysisResult
from qrest_model.analysis.modal import modal_analysis
from qrest_model.common.io import ensure_output_dir
from qrest_model.exporters.time_history import write_csv
from qrest_model.schema import (
    EULER_BEAM_2D,
    RAYLEIGH_BEAM_2D,
    RIGID_FLOOR_SHEAR_3D,
    SHEAR_FLEXURE_BUILDING_2D,
    SHEAR_BUILDING_1D,
    TIMOSHENKO_BEAM_2D,
)

if TYPE_CHECKING:
    from qrest_model.datasets.cases import DatasetCase


def write_structural_properties(case: "DatasetCase", output_dir: str | Path, result: AnalysisResult | dict[str, Any]) -> None:
    output = ensure_output_dir(output_dir)
    mass = _mass_matrix(result)
    stiffness = _stiffness_matrix(result)
    damping = _damping_matrix(result)
    dof_labels = dof_labels_for_case(case)
    modal = modal_properties(result)

    write_matrix_csv(output / "mass_matrix.csv", mass, dof_labels, dof_labels)
    write_matrix_csv(output / "stiffness_matrix.csv", stiffness, dof_labels, dof_labels)
    write_matrix_csv(output / "damping_matrix.csv", damping, dof_labels, dof_labels)
    write_modal_frequencies(output / "modal_frequencies.csv", modal["omega"])
    write_mode_shapes(output / "mode_shapes.csv", dof_labels, modal["mass_normalized_modes"])
    write_csv(output / "story_stiffness.csv", _story_stiffness_rows(result))

    summary = {
        "case": case.name,
        "model_type": case.model_type,
        "dof_count": int(mass.shape[0]),
        "mode_count": int(modal["omega"].size),
        "fundamental_frequency_hz": float(modal["omega"][0] / (2.0 * np.pi)) if modal["omega"].size else None,
        "fundamental_period_s": float(2.0 * np.pi / modal["omega"][0]) if modal["omega"].size else None,
        "rayleigh_alpha": _metadata_value(result, "rayleigh_alpha"),
        "rayleigh_beta": _metadata_value(result, "rayleigh_beta"),
        "matrix_files_are_labelled": True,
        "mode_shape_normalization": "mass-normalized; each mode satisfies phi.T @ M @ phi = 1",
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def dof_labels_for_case(case: "DatasetCase") -> list[str]:
    if case.model_type in {"shear1d", SHEAR_BUILDING_1D}:
        direction = str(case.config.get("model", {}).get("dof_per_floor", ["Ux"])[0])[-1].lower()
        return [
            f"story_{story:02d}_{direction}"
            for story in range(1, case.config["model"]["num_stories"] + 1)
        ]
    if case.model_type in {EULER_BEAM_2D, RAYLEIGH_BEAM_2D, TIMOSHENKO_BEAM_2D, SHEAR_FLEXURE_BUILDING_2D}:
        return [
            f"story_{story:02d}_{component}"
            for story in range(1, case.config["model"]["num_stories"] + 1)
            for component in ("u", "theta")
        ]
    if case.model_type not in {"story3d", RIGID_FLOOR_SHEAR_3D}:
        raise ValueError(f"Unsupported structural properties model_type: {case.model_type}")
    return [
        f"story_{story:02d}_{component}"
        for story in range(1, case.config["model"]["num_stories"] + 1)
        for component in ("x", "y", "rz")
    ]


def modal_properties(result: AnalysisResult | dict[str, Any] | np.ndarray, stiffness: np.ndarray | None = None) -> dict[str, np.ndarray]:
    if isinstance(result, AnalysisResult):
        if result.modal is None:
            raise ValueError("AnalysisResult.modal is required for structural property export.")
        modal = result.modal
    elif stiffness is None:
        mass = np.asarray(result["mass_matrix"], dtype=float)
        stiffness = np.asarray(result["stiffness_matrix"], dtype=float)
        modal = modal_analysis(mass, stiffness)
    else:
        modal = modal_analysis(np.asarray(result, dtype=float), stiffness)
    return {"omega": modal.omega, "mass_normalized_modes": modal.mode_shapes}


def _mass_matrix(result: AnalysisResult | dict[str, Any]) -> np.ndarray:
    if isinstance(result, AnalysisResult):
        return result.mass_matrix
    return np.asarray(result["mass_matrix"], dtype=float)


def _stiffness_matrix(result: AnalysisResult | dict[str, Any]) -> np.ndarray:
    if isinstance(result, AnalysisResult):
        return result.stiffness_matrix
    return np.asarray(result["stiffness_matrix"], dtype=float)


def _damping_matrix(result: AnalysisResult | dict[str, Any]) -> np.ndarray:
    if isinstance(result, AnalysisResult):
        return result.damping_matrix
    return np.asarray(result["damping_matrix"], dtype=float)


def _story_stiffness_rows(result: AnalysisResult | dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(result, AnalysisResult):
        return result.story_stiffness_rows
    return result["story_stiffness_rows"]


def _metadata_value(result: AnalysisResult | dict[str, Any], key: str) -> Any:
    if isinstance(result, AnalysisResult):
        return getattr(result.metadata, key)
    return result.get("metadata", {}).get(key)


def write_matrix_csv(path: str | Path, matrix: np.ndarray, row_labels: list[str], col_labels: list[str]) -> None:
    rows = []
    for row_index, row_label in enumerate(row_labels):
        row: dict[str, Any] = {"dof": row_label}
        for col_index, col_label in enumerate(col_labels):
            row[col_label] = matrix[row_index, col_index]
        rows.append(row)
    write_csv(path, rows)


def write_modal_frequencies(path: str | Path, omega: np.ndarray) -> None:
    rows = []
    for index, value in enumerate(omega, start=1):
        rows.append(
            {
                "mode": index,
                "circular_frequency_rad_s": value,
                "frequency_hz": value / (2.0 * np.pi),
                "period_s": 2.0 * np.pi / value,
            }
        )
    write_csv(path, rows)


def write_mode_shapes(path: str | Path, dof_labels: list[str], modes: np.ndarray) -> None:
    rows = []
    for row_index, label in enumerate(dof_labels):
        row: dict[str, Any] = {"dof": label}
        for mode_index in range(modes.shape[1]):
            row[f"mode_{mode_index + 1:02d}"] = modes[row_index, mode_index]
        rows.append(row)
    write_csv(path, rows)
