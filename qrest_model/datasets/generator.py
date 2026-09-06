"""Dataset generation workflow."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Iterable

from qrest_model.analysis.result import AnalysisResult
from qrest_model.backends import run_analysis
from qrest_model.common.io import ensure_output_dir
from qrest_model.datasets.cases import DATASET_CONFIG_ROOT, DatasetCase, dataset_cases
from qrest_model.schema import SHEAR_BUILDING_1D
from qrest_model.exporters.algorithm_config import write_algorithm_configs
from qrest_model.exporters.structural_properties import write_structural_properties
from qrest_model.exporters.time_history import (
    write_shear_master_time_history,
    write_story3d_master_time_history,
)
from qrest_model.postprocess.master_mapping import map_sensors


def generate_all(
    output_root: str | Path,
    selected_names: Iterable[str] | None = None,
    config_root: str | Path = DATASET_CONFIG_ROOT,
) -> list[Path]:
    selected = set(selected_names or [])
    cases = dataset_cases(config_root)
    available = {case.name for case in cases}
    unknown = selected - available
    if unknown:
        raise ValueError(
            f"Unknown dataset case(s): {', '.join(sorted(unknown))}. "
            f"Available cases: {', '.join(sorted(available))}"
        )
    output_root = ensure_output_dir(output_root) if selected else reset_output_dir(output_root)
    generated: list[Path] = []
    for case in cases:
        if selected and case.name not in selected:
            continue
        generated.append(generate_case(case, output_root / case.name))
    return generated


def generate_case(case: DatasetCase, case_dir: str | Path) -> Path:
    return generate_official_case(case, case_dir)


def generate_official_case(case: DatasetCase, case_dir: str | Path) -> Path:
    case_dir = reset_output_dir(case_dir)
    config_path = case_dir / "config.json"
    config_path.write_text(
        json.dumps(case.config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    result = run_analysis(config_path, backend="direct")

    master_dir = ensure_output_dir(case_dir / "master_time_history")
    if case.model_type == SHEAR_BUILDING_1D:
        write_shear_master_time_history(master_dir, result, case.config)
    else:
        write_story3d_master_time_history(master_dir, result)
    write_structural_properties(case, case_dir / "structural_properties", result)

    time_history_dir = ensure_output_dir(case_dir / "time_history")
    map_sensors(
        case.config,
        master_dir,
        time_history_dir,
        metadata_output=case_dir / "metadata.json",
        project_name=f"qREST_Model_{case.name}",
        event_name=f"MODEL_{case.name.upper()}",
    )
    dataset_info = build_dataset_info(case, result)
    (case_dir / "dataset_info.json").write_text(
        json.dumps(dataset_info, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_algorithm_configs(case_dir)
    return case_dir


def reset_output_dir(path: str | Path) -> Path:
    output = Path(path)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    return output


def build_dataset_info(case: DatasetCase, result: AnalysisResult) -> dict[str, Any]:
    return {
        "name": case.name,
        "data_type": case.data_type,
        "model_type": case.model_type,
        "description": case.description,
        "time_steps": int(result.time.size),
        "master_time_history": {
            "directory": "master_time_history",
            "format": "CSV; first column is time, each remaining column is one master mass-point component.",
        },
        "sensor_time_history": {
            "directory": "time_history",
            "format": "CSV; first column is time, each remaining column is one configured sensor channel.",
            "sensor_stories": sensor_stories(case.config),
        },
        "structural_properties": {
            "directory": "structural_properties",
            "files": {
                "mass_matrix": "structural_properties/mass_matrix.csv",
                "stiffness_matrix": "structural_properties/stiffness_matrix.csv",
                "damping_matrix": "structural_properties/damping_matrix.csv",
                "modal_frequencies": "structural_properties/modal_frequencies.csv",
                "mode_shapes": "structural_properties/mode_shapes.csv",
                "story_stiffness": "structural_properties/story_stiffness.csv",
                "summary": "structural_properties/summary.json",
            },
        },
        "algorithm_config": {
            "directory": "config",
            "source": "generated from this dataset's metadata, structural_properties, and model footprint.",
            "oma_note": (
                "Current OMA post-processing rejects MIXED_DIRECTION datasets; this config is still generated for future algorithm research."
                if case.name == "staggered_2x_center_y"
                else "Supported by current OMA tests."
            ),
        },
        "metadata_file": "metadata.json",
    }


def sensor_stories(config: dict[str, Any]) -> list[int]:
    return sorted({int(sensor["story"]) for sensor in config.get("sensors", [])})
