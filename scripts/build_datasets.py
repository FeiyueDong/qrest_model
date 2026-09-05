from __future__ import annotations

import argparse

from qrest_model.datasets.cases import (
    CONFIG_ROOT,
    DATASET_CONFIG_ROOT,
    MODEL_ROOT,
    DatasetCase,
    corner_elements as _corner_elements,
    dataset_cases,
    expand_floor_defaults as _expand_floor_defaults,
    expand_model_config as _expand_model_config,
    expand_sensor_specs as _expand_sensor_specs,
    expand_stories as _expand_stories,
    load_dataset_case,
    resolve_config_path as _resolve_config_path,
    resolve_ground_motion_paths as _resolve_ground_motion_paths,
    schema_model_type as _schema_model_type,
    two_x_story_sensors as _two_x_story_sensors,
)
from qrest_model.datasets.generator import (
    build_dataset_info as _dataset_info,
    generate_all,
    generate_case,
    generate_official_case as _generate_official_case,
    reset_output_dir as _reset_output_dir,
    sensor_stories as _sensor_stories,
)
from qrest_model.datasets.validation import (
    validate_opensees_sensor_nodes as _validate_opensees_sensor_nodes,
)
from qrest_model.exporters.structural_properties import (
    dof_labels_for_case as _dof_labels,
    modal_properties as _modal_properties,
    write_matrix_csv as _write_matrix_csv,
    write_modal_frequencies as _write_modal_frequencies,
    write_mode_shapes as _write_mode_shapes,
    write_structural_properties as _write_structural_properties,
)
from qrest_model.exporters.time_history import (
    load_ground_motion_from_raw as _load_ground_motion_from_raw,
    write_csv as _write_csv,
    write_shear_master_time_history as _write_shear_master_time_history,
    write_story3d_master_time_history as _write_story3d_master_time_history,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate qREST model test datasets.")
    parser.add_argument(
        "--output-root",
        default=str(MODEL_ROOT / "output" / "test_datasets"),
        help="Directory where case subdirectories are written.",
    )
    parser.add_argument(
        "--config-root",
        default=str(DATASET_CONFIG_ROOT),
        help="Directory containing dataset generation JSON configs.",
    )
    parser.add_argument(
        "--case",
        action="append",
        help="Generate only the selected case. May be repeated.",
    )
    args = parser.parse_args()
    generated = generate_all(args.output_root, args.case, args.config_root)
    for path in generated:
        print(path)


if __name__ == "__main__":
    main()
