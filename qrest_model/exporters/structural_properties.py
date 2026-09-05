"""Structural property exporters for generated datasets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from qrest_model.analysis.modal import modal_analysis
from qrest_model.common.io import ensure_output_dir
from qrest_model.datasets.cases import DatasetCase
from qrest_model.exporters.time_history import write_csv


def write_structural_properties(case: DatasetCase, output_dir: str | Path, result: dict[str, Any]) -> None:
    output = ensure_output_dir(output_dir)
    mass = np.asarray(result["mass_matrix"], dtype=float)
    stiffness = np.asarray(result["stiffness_matrix"], dtype=float)
    damping = np.asarray(result["damping_matrix"], dtype=float)
    dof_labels = dof_labels_for_case(case)
    modal = modal_properties(mass, stiffness)

    write_matrix_csv(output / "mass_matrix.csv", mass, dof_labels, dof_labels)
    write_matrix_csv(output / "stiffness_matrix.csv", stiffness, dof_labels, dof_labels)
    write_matrix_csv(output / "damping_matrix.csv", damping, dof_labels, dof_labels)
    write_modal_frequencies(output / "modal_frequencies.csv", modal["omega"])
    write_mode_shapes(output / "mode_shapes.csv", dof_labels, modal["mass_normalized_modes"])
    write_csv(output / "story_stiffness.csv", result["story_stiffness_rows"])

    summary = {
        "case": case.name,
        "model_type": case.model_type,
        "dof_count": int(mass.shape[0]),
        "mode_count": int(modal["omega"].size),
        "fundamental_frequency_hz": float(modal["omega"][0] / (2.0 * np.pi)) if modal["omega"].size else None,
        "fundamental_period_s": float(2.0 * np.pi / modal["omega"][0]) if modal["omega"].size else None,
        "rayleigh_alpha": result.get("metadata", {}).get("rayleigh_alpha"),
        "rayleigh_beta": result.get("metadata", {}).get("rayleigh_beta"),
        "matrix_files_are_labelled": True,
        "mode_shape_normalization": "mass-normalized; each mode satisfies phi.T @ M @ phi = 1",
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def dof_labels_for_case(case: DatasetCase) -> list[str]:
    if case.model_type == "shear1d":
        direction = str(case.config.get("model", {}).get("dof_per_floor", ["Ux"])[0])[-1].lower()
        return [
            f"story_{story:02d}_{direction}"
            for story in range(1, case.config["model"]["num_stories"] + 1)
        ]
    return [
        f"story_{story:02d}_{component}"
        for story in range(1, case.config["model"]["num_stories"] + 1)
        for component in ("x", "y", "rz")
    ]


def modal_properties(mass: np.ndarray, stiffness: np.ndarray) -> dict[str, np.ndarray]:
    modal = modal_analysis(mass, stiffness)
    return {"omega": modal.omega, "mass_normalized_modes": modal.mode_shapes}


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
