"""Comparison helpers for backend outputs."""

from __future__ import annotations

from pathlib import Path
import csv
from typing import Any

import numpy as np


def compare_master_arrays(a: dict[str, Any], b: dict[str, Any]) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for key in ("displacement", "velocity", "acceleration"):
        diff = np.asarray(a[key]) - np.asarray(b[key])
        denom = max(np.linalg.norm(np.asarray(a[key])), np.linalg.norm(np.asarray(b[key])), 1.0)
        metrics[f"{key}_max_abs"] = float(np.max(np.abs(diff)))
        metrics[f"{key}_relative_l2"] = float(np.linalg.norm(diff) / denom)
    return metrics


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
        denom = max(float(np.linalg.norm(a)), float(np.linalg.norm(b)), 1.0)
        metrics[f"{key}_max_abs"] = float(np.max(np.abs(a - b)))
        metrics[f"{key}_relative_l2"] = float(np.linalg.norm(a - b) / denom)
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
