"""Comparison helpers for backend outputs."""

from __future__ import annotations

from pathlib import Path
import csv
from typing import Any

import numpy as np

from qrest_model.analysis.result import AnalysisResult


RELATIVE_ERROR_EPS = 1.0e-30


def compare_master_arrays(a: AnalysisResult | dict[str, Any], b: AnalysisResult | dict[str, Any]) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for key in ("displacement", "velocity", "acceleration"):
        a_values = _response_array(a, key)
        b_values = _response_array(b, key)
        diff = a_values - b_values
        metrics[f"{key}_max_abs"] = float(np.max(np.abs(diff)))
        metrics[f"{key}_relative_l2"] = symmetric_relative_l2(a_values, b_values)
    return metrics


def symmetric_relative_l2(a: np.ndarray, b: np.ndarray, *, eps: float = RELATIVE_ERROR_EPS) -> float:
    """Return the symmetric relative L2 error between two numeric arrays."""

    a_norm = float(np.linalg.norm(a))
    b_norm = float(np.linalg.norm(b))
    return float(2.0 * np.linalg.norm(a - b) / (a_norm + b_norm + eps))


def _response_array(result: AnalysisResult | dict[str, Any], key: str) -> np.ndarray:
    if isinstance(result, AnalysisResult):
        return np.asarray(getattr(result.relative, key), dtype=float)
    return np.asarray(result[key], dtype=float)


def compare_master_csv(path_a: str | Path, path_b: str | Path) -> dict[str, float]:
    rows_a = _read_numeric_rows(path_a)
    rows_b = _read_numeric_rows(path_b)
    if len(rows_a) != len(rows_b):
        raise ValueError("CSV files have different row counts.")
    metrics: dict[str, float] = {}
    skip_keys = {"time", "story"}
    keys = sorted((set(rows_a[0]) & set(rows_b[0])) - skip_keys)
    for key in keys:
        a = np.array([row[key] for row in rows_a])
        b = np.array([row[key] for row in rows_b])
        metrics[f"{key}_max_abs"] = float(np.max(np.abs(a - b)))
        metrics[f"{key}_relative_l2"] = symmetric_relative_l2(a, b)
    return metrics


def _read_numeric_rows(path: str | Path) -> list[dict[str, float]]:
    with Path(path).open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for row in reader:
            numeric_row = {}
            for key, value in row.items():
                try:
                    numeric_row[key] = float(value)
                except (TypeError, ValueError):
                    continue
            rows.append(numeric_row)
        return rows
