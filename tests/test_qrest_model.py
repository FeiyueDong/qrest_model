from __future__ import annotations
import json
import os

from qrest_model.analysis.linear_system import LinearSystem
from qrest_model.analysis.modal import modal_analysis
from qrest_model.analysis.newmark import NewmarkSolver
from qrest_model.analysis.result import AnalysisResult
from qrest_model.backends.base import DirectBackend, run_analysis
from qrest_model.cli import main as cli_main
from qrest_model.theory.story_stiffness import story_stiffness
from qrest_model.theory.shear_stiffness import assemble_shear_stiffness
from qrest_model.postprocess.sensor_mapping import map_floor_motion
from qrest_model.schema import load_shear_config, normalize_shear_config
from qrest_model.common.ground_motion import load_ground_motion
from qrest_model.schema import load_config, normalize_config
from qrest_model.datasets.cases import DATASET_CONFIG_ROOT, DatasetCase, dataset_cases
from qrest_model.datasets.validation import validate_opensees_sensor_nodes
from qrest_model.exporters.qrest_dataset import export_dataset
from qrest_model.exporters.structural_properties import write_structural_properties
from qrest_model.exporters.time_history import write_story3d_master_time_history
from qrest_model.backends.direct_shear import run as run_direct_shear
from qrest_model.backends.direct_shear import run_result as run_direct_shear_result
from qrest_model.backends.direct_stiffness import run
from qrest_model.backends.direct_stiffness import run_result as run_direct_stiffness_result
from scripts import build_datasets as legacy_build_datasets
from scripts import export_datasets as legacy_export_datasets
from scripts.make_metadata import build_qrest_metadata
from scripts.make_algorithm_configs import write_algorithm_configs
from scripts.map_sensors import map_sensors
try:
    from py_algorithm.data_struct.metadata import Metadata
except ImportError:
    Metadata = None  # type: ignore[assignment]

from pathlib import Path
import sys

import numpy as np
import pytest

MODEL_ROOT = Path(__file__).resolve().parents[1]
if str(MODEL_ROOT) not in sys.path:
    sys.path.insert(0, str(MODEL_ROOT))


def _base_raw(num_stories: int = 3) -> dict:
    return {
        "schema_version": "2.0",
        "model": {
            "type": "rigid_floor_shear_3d",
            "num_stories": num_stories,
            "dof_per_floor": ["Ux", "Uy", "Rz"],
            "coordinate_reference": "geometry_center",
        },
        "floor_defaults": {
            "mass": 1.0e6,
            "jz": 8.0e6,
            "mass_center": [0.0, 0.0],
            "elements": [
                {"id": "corner_sw", "x": -5.0, "y": -3.0, "kx": 2.0e8, "ky": 2.0e8},
                {"id": "corner_se", "x": 5.0, "y": -3.0, "kx": 2.0e8, "ky": 2.0e8},
                {"id": "corner_ne", "x": 5.0, "y": 3.0, "kx": 2.0e8, "ky": 2.0e8},
                {"id": "corner_nw", "x": -5.0, "y": 3.0, "kx": 2.0e8, "ky": 2.0e8},
            ],
        },
        "stories": [{"story": i + 1} for i in range(num_stories)],
        "sensors": [
            {"id": "roof_center_x", "story": num_stories,
                "x": 0.0, "y": 0.0, "direction": "X"},
            {"id": "roof_corner_x", "story": num_stories,
                "x": 5.0, "y": 3.0, "direction": "X"},
        ],
        "damping": {"type": "rayleigh", "zeta": 0.02, "modes": [1, 3]},
        "ground_motion": {
            "dt": 0.01,
            "duration": 1.0,
            "synthetic": {"amplitude_x": 0.12, "amplitude_y": 0.0, "frequency_x": 1.0},
        },
    }


def test_legacy_config_warns_and_infers_schema_fields() -> None:
    raw = _base_raw()
    del raw["schema_version"]
    del raw["model"]["type"]

    with pytest.warns(UserWarning, match="Missing schema_version"):
        with pytest.warns(UserWarning, match="Missing model.type"):
            config = normalize_config(raw)

    assert config.schema_version == "legacy"
    assert config.model_type == "rigid_floor_shear_3d"


def test_common_config_modules_reexport_schema_entry_points() -> None:
    from qrest_model.common import config as legacy_config
    from qrest_model.common import shear_config as legacy_shear_config

    assert legacy_config.normalize_config is normalize_config
    assert legacy_shear_config.normalize_shear_config is normalize_shear_config


def test_schema_version_and_model_type_are_strict() -> None:
    raw = _base_raw()
    raw["schema_version"] = "1.0"
    with pytest.raises(ValueError, match="Unsupported schema_version"):
        normalize_config(raw)

    raw = _base_raw()
    raw["model"]["type"] = "shear_building_1d"
    with pytest.raises(ValueError, match="Unsupported model.type"):
        normalize_config(raw)


def test_rayleigh_modes_are_not_silently_truncated() -> None:
    raw = _base_raw()
    raw["damping"] = {"type": "rayleigh", "zeta": 0.02, "modes": [1, 2, 3]}

    with pytest.raises(ValueError, match="exactly two"):
        normalize_config(raw)


def test_duplicate_sensor_ids_are_rejected() -> None:
    raw = _base_raw()
    raw["sensors"] = [
        {"id": "dup", "story": 1, "x": 0.0, "y": 0.0, "direction": "X"},
        {"id": "dup", "story": 2, "x": 0.0, "y": 0.0, "direction": "X"},
    ]

    with pytest.raises(ValueError, match="Sensor ID 'dup'"):
        normalize_config(raw)


def test_symmetric_structure_x_input_has_near_zero_torsion() -> None:
    config = normalize_config(_base_raw())
    result = run(config)
    rz = result["displacement"][:, :, 2]
    assert np.max(np.abs(rz)) < 1.0e-12


def test_eccentric_direct_stiffness_excites_torsion() -> None:
    raw = _base_raw()
    raw["floor_defaults"] = {
        "mass": 1.0e6,
        "jz": 8.0e6,
        "mass_center": [0.0, 0.0],
        "direct_stiffness": {
            "kx": 8.0e8,
            "ky": 8.0e8,
            "ktheta": 2.5e10,
            "stiffness_center": [0.0, 0.8],
        },
    }
    config = normalize_config(raw)
    result = run(config)
    rz = result["displacement"][:, :, 2]
    assert np.max(np.abs(rz)) > 1.0e-8


def test_direct_backend_exposes_absolute_translational_response() -> None:
    config = normalize_config(_base_raw(num_stories=2))
    result = run(config)
    ground_acc = result["ground_acceleration"]

    assert result["absolute_displacement"].shape == result["displacement"].shape
    assert result["absolute_velocity"].shape == result["velocity"].shape
    assert result["absolute_acceleration"].shape == result["acceleration"].shape
    assert np.allclose(
        result["absolute_acceleration"][:, :, 0],
        result["acceleration"][:, :, 0] + ground_acc[:, 0, None],
    )
    assert np.allclose(
        result["absolute_acceleration"][:, :, 1],
        result["acceleration"][:, :, 1] + ground_acc[:, 1, None],
    )
    assert "abs_ax" in result["sensor_rows"][0]
    assert "relative_value" in result["sensor_rows"][0]


def test_direct_stiffness_run_result_matches_legacy_dict() -> None:
    config = normalize_config(_base_raw(num_stories=2))

    structured = run_direct_stiffness_result(config)
    legacy = run(config)
    converted = structured.to_legacy_dict()

    assert isinstance(structured, AnalysisResult)
    for key in ("displacement", "velocity", "acceleration", "absolute_acceleration"):
        assert np.allclose(converted[key], legacy[key])
    assert converted["metadata"]["backend"] == "direct_stiffness"
    assert converted["sensor_rows"][0]["node_or_sensor_id"] == legacy["sensor_rows"][0]["node_or_sensor_id"]


def test_direct_backend_unified_entry_runs_rigid_floor_case() -> None:
    result = run_analysis(_base_raw(num_stories=2), backend="direct")

    assert isinstance(result, AnalysisResult)
    assert result.metadata.backend == "direct_stiffness"
    assert result.relative.displacement.shape == (101, 2, 3)


def test_cli_run_writes_direct_backend_outputs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "run_output"

    exit_code = cli_main([
        "run",
        "story3d/configs/default_10story.json",
        "--backend",
        "direct",
        "--output",
        str(output),
    ])

    assert exit_code == 0
    assert (output / "master_response.csv").exists()
    assert (output / "sensor_response.csv").exists()
    assert str(output) in capsys.readouterr().out


def test_invalid_sensor_story_reports_clear_error() -> None:
    raw = _base_raw(num_stories=2)
    raw["sensors"] = [{"id": "bad", "story": 3,
                       "x": 0.0, "y": 0.0, "direction": "X"}]

    try:
        normalize_config(raw)
    except ValueError as exc:
        assert "outside the model" in str(exc)
    else:
        raise AssertionError(
            "normalize_config should reject out-of-range sensor stories")


def test_sensor_mapping_uses_rigid_floor_formula() -> None:
    floor_values = np.array([[1.0, 2.0, 0.1]])
    mapped = map_floor_motion(floor_values, x=5.0, y=3.0)
    assert np.allclose(mapped[0], [0.7, 2.5, 0.1])


def test_story_stiffness_symmetric_layout_has_no_coupling() -> None:
    config = normalize_config(_base_raw(num_stories=1))
    stiffness = story_stiffness(config.stories[0])
    assert np.allclose(stiffness[0, 2], 0.0)
    assert np.allclose(stiffness[1, 2], 0.0)
    assert np.allclose(stiffness, stiffness.T)


def test_newmark_solver_rejects_nonuniform_time_steps() -> None:
    system = LinearSystem(
        mass=np.eye(1),
        damping=np.zeros((1, 1)),
        stiffness=np.eye(1),
        influence=np.ones(1),
    )

    with pytest.raises(ValueError, match="time step must be constant"):
        NewmarkSolver().solve(system, np.array([0.0, 0.1, 0.25]), np.zeros(3))


def test_modal_analysis_returns_mass_normalized_modes() -> None:
    mass = np.diag([2.0, 1.0])
    stiffness = np.array([[6.0, -2.0], [-2.0, 4.0]])

    modal = modal_analysis(mass, stiffness)
    pivots = np.argmax(np.abs(modal.mode_shapes), axis=0)

    assert np.all(np.diff(modal.omega) > 0.0)
    assert np.all(modal.mode_shapes[pivots, range(2)] > 0.0)
    assert np.allclose(modal.mode_shapes.T @ mass @ modal.mode_shapes, np.eye(2))
    assert np.allclose(modal.frequency, modal.omega / (2.0 * np.pi))


def test_variable_16story_external_ground_motion_config() -> None:
    config_path = MODEL_ROOT / "story3d" / "configs" / \
        "variable_stiffness_16story_external_gm.json"
    config = load_config(config_path)
    ground = load_ground_motion(config.ground_motion, config_path.parent)
    bottom = story_stiffness(config.stories[0])
    top = story_stiffness(config.stories[-1])

    assert config.num_stories == 16
    assert len(ground["time"]) == 15000
    assert np.isclose(ground["time"][-1], 149.99)
    assert np.isclose(top[0, 0] / bottom[0, 0], 0.8)
    assert np.isclose(top[1, 1] / bottom[1, 1], 0.8)


def test_one_direction_shear_stiffness_assembly() -> None:
    config = normalize_shear_config(
        {
            "schema_version": "2.0",
            "model": {"type": "shear_building_1d", "num_stories": 3, "dof_per_floor": ["Ux"]},
            "floor_defaults": {"mass": 1.0, "stiffness": 10.0},
            "stories": [{"story": 1}, {"story": 2, "stiffness": 8.0}, {"story": 3, "stiffness": 6.0}],
            "damping": {"type": "rayleigh", "zeta": 0.02, "modes": [1, 2]},
            "ground_motion": {"dt": 0.01, "duration": 0.1},
        }
    )
    stiffness = assemble_shear_stiffness(config.stories)
    assert np.allclose(
        stiffness,
        np.array([[18.0, -8.0, 0.0], [-8.0, 14.0, -6.0], [0.0, -6.0, 6.0]]),
    )


def test_one_direction_shear_direct_backend_runs() -> None:
    config = normalize_shear_config(
        {
            "schema_version": "2.0",
            "model": {"type": "shear_building_1d", "num_stories": 3, "dof_per_floor": ["Ux"]},
            "floor_defaults": {"mass": 1.0e6, "stiffness": 8.0e8},
            "stories": [{"story": 1}, {"story": 2}, {"story": 3}],
            "sensors": [{"id": "roof_accel", "story": 3, "quantity": "accel"}],
            "damping": {"type": "rayleigh", "zeta": 0.02, "modes": [1, 2]},
            "ground_motion": {
                "dt": 0.01,
                "duration": 0.5,
                "synthetic": {"amplitude_x": 0.1, "amplitude_y": 0.0, "frequency_x": 1.0},
            },
        }
    )
    result = run_direct_shear(config)
    assert result["displacement"].shape == (51, 3)
    assert result["velocity"].shape == (51, 3)
    assert result["acceleration"].shape == (51, 3)
    assert len(result["sensor_rows"]) == 51


def test_direct_shear_run_result_matches_legacy_dict() -> None:
    config = normalize_shear_config(
        {
            "schema_version": "2.0",
            "model": {"type": "shear_building_1d", "num_stories": 3, "dof_per_floor": ["Ux"]},
            "floor_defaults": {"mass": 1.0e6, "stiffness": 8.0e8},
            "stories": [{"story": 1}, {"story": 2}, {"story": 3}],
            "sensors": [{"id": "roof_accel", "story": 3, "quantity": "accel"}],
            "damping": {"type": "rayleigh", "zeta": 0.02, "modes": [1, 2]},
            "ground_motion": {
                "dt": 0.01,
                "duration": 0.5,
                "synthetic": {"amplitude_x": 0.1, "amplitude_y": 0.0, "frequency_x": 1.0},
            },
        }
    )

    structured = run_direct_shear_result(config)
    legacy = run_direct_shear(config)
    converted = structured.to_legacy_dict()

    assert isinstance(structured, AnalysisResult)
    for key in ("displacement", "velocity", "acceleration"):
        assert np.allclose(converted[key], legacy[key])
    assert converted["metadata"]["backend"] == "direct_shear"
    assert converted["metadata"]["direction"] == "X"


def test_direct_backend_unified_entry_routes_shear_path(tmp_path: Path) -> None:
    case_path = tmp_path / "shear.json"
    case_path.write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "model": {"type": "shear_building_1d", "num_stories": 2, "dof_per_floor": ["Ux"]},
                "floor_defaults": {"mass": 1.0e6, "stiffness": 8.0e8},
                "stories": [{"story": 1}, {"story": 2}],
                "sensors": [{"id": "roof_accel", "story": 2, "quantity": "accel"}],
                "damping": {"type": "rayleigh", "zeta": 0.02, "modes": [1, 2]},
                "ground_motion": {
                    "dt": 0.01,
                    "duration": 0.1,
                    "synthetic": {"amplitude_x": 0.1, "amplitude_y": 0.0, "frequency_x": 1.0},
                },
            }
        ),
        encoding="utf-8",
    )

    result = DirectBackend().run(case_path)

    assert result.metadata.backend == "direct_shear"
    assert result.relative.displacement.shape == (11, 2)


def test_cli_validate_can_compare_direct_backend_to_itself(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    metrics = tmp_path / "metrics.txt"

    exit_code = cli_main([
        "validate",
        "shear1d/configs/shear_16story_external_gm.json",
        "--backend-a",
        "direct",
        "--backend-b",
        "direct",
        "--output",
        str(metrics),
        "--tolerance",
        "0.0",
    ])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "displacement_max_abs: 0.000000e+00" in output
    assert metrics.read_text(encoding="utf-8") == output


def test_shear_config_rejects_duplicate_stories_and_nonpositive_values() -> None:
    with pytest.raises(ValueError, match="defined more than once"):
        normalize_shear_config(
            {
                "schema_version": "2.0",
                "model": {"type": "shear_building_1d", "num_stories": 2, "dof_per_floor": ["Ux"]},
                "floor_defaults": {"mass": 1.0, "stiffness": 10.0},
                "stories": [{"story": 1}, {"story": 1}],
                "damping": {"type": "rayleigh", "zeta": 0.02, "modes": [1, 2]},
                "ground_motion": {"dt": 0.01, "duration": 0.1},
            }
        )

    with pytest.raises(ValueError, match="mass and stiffness must be positive"):
        normalize_shear_config(
            {
                "schema_version": "2.0",
                "model": {"type": "shear_building_1d", "num_stories": 2, "dof_per_floor": ["Ux"]},
                "floor_defaults": {"mass": -1.0, "stiffness": 10.0},
                "stories": [{"story": 1}, {"story": 2}],
                "damping": {"type": "rayleigh", "zeta": 0.02, "modes": [1, 2]},
                "ground_motion": {"dt": 0.01, "duration": 0.1},
            }
        )


def test_one_direction_16story_external_ground_motion_config() -> None:
    config_path = MODEL_ROOT / "shear1d" / \
        "configs" / "shear_16story_external_gm.json"
    config = load_shear_config(config_path)
    ground = load_ground_motion(config.ground_motion, config_path.parent)
    bottom = config.stories[0].stiffness
    top = config.stories[-1].stiffness

    assert config.num_stories == 16
    assert config.direction == "X"
    assert len(ground["time"]) == 15000
    assert np.max(np.abs(ground["ax"])) > 0.0
    assert np.isclose(top / bottom, 0.8)


def test_generated_dataset_case_definitions_cover_requested_channel_forms() -> None:
    cases = {case.name: case for case in dataset_cases()}
    config_names = {path.stem for path in DATASET_CONFIG_ROOT.glob("*.json")}

    assert set(cases) == {
        "single_x",
        "dual_xy",
        "two_x_one_y_torsion",
        "two_x_torsion",
        "staggered_2x_center_y",
    }
    assert config_names == set(cases)
    assert cases["single_x"].model_type == "shear1d"
    assert {sensor["story"] for sensor in cases["dual_xy"].config["sensors"]} == {1, 3, 7, 11, 16}
    assert {sensor.get("direction", "X") for sensor in cases["dual_xy"].config["sensors"]} == {"X", "Y"}
    assert len(cases["two_x_one_y_torsion"].config["sensors"]) == 15
    assert len(cases["two_x_torsion"].config["sensors"]) == 10
    assert len(cases["staggered_2x_center_y"].config["sensors"]) == 15
    assert cases["two_x_one_y_torsion"].config["ground_motion"]["dt"] == 0.02
    assert cases["two_x_one_y_torsion"].config["floor_defaults"]["mass_center"] != [0.0, 0.0]
    assert cases["two_x_one_y_torsion"].config["stories"] == [{"story": story} for story in range(1, 17)]
    staggered_sensors = cases["staggered_2x_center_y"].config["sensors"]
    assert [sensor["id"] for sensor in staggered_sensors[:4]] == [
        "01f_x_yneg",
        "01f_x_ypos",
        "03f_x_yneg",
        "03f_x_ypos",
    ]
    assert [sensor["id"] for sensor in staggered_sensors[-5:]] == [
        "01f_center_y",
        "04f_center_y",
        "08f_center_y",
        "12f_center_y",
        "16f_center_y",
    ]
    assert {
        sensor["story"]
        for sensor in staggered_sensors
        if sensor["direction"] == "X"
    } == {1, 3, 7, 11, 16}
    assert {
        sensor["story"]
        for sensor in staggered_sensors
        if sensor["direction"] == "Y"
    } == {1, 4, 8, 12, 16}


def test_build_datasets_script_reexports_library_entry_points() -> None:
    assert legacy_build_datasets.dataset_cases is dataset_cases
    assert legacy_build_datasets._write_structural_properties is write_structural_properties


def test_export_datasets_script_reexports_library_entry_points() -> None:
    assert legacy_export_datasets.export_dataset is export_dataset


def test_cli_generate_datasets_runs_selected_case(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output_root = tmp_path / "datasets"

    exit_code = cli_main([
        "generate-datasets",
        "--output-root",
        str(output_root),
        "--case",
        "single_x",
    ])

    assert exit_code == 0
    assert (output_root / "single_x" / "metadata.json").exists()
    assert str(output_root / "single_x") in capsys.readouterr().out


def test_cli_export_qrest_exports_generated_case(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    generated_root = tmp_path / "generated"
    exported_root = tmp_path / "exported"
    cli_main(["generate-datasets", "--output-root", str(generated_root), "--case", "single_x"])
    capsys.readouterr()

    exit_code = cli_main([
        "export-qrest",
        "--input",
        str(generated_root / "single_x"),
        "--output",
        str(exported_root),
    ])

    exported = exported_root / "single_x"
    assert exit_code == 0
    assert (exported / "single_x_metadata.json").exists()
    assert (exported / "single_x_data.txt").exists()
    assert str(exported) in capsys.readouterr().out


def test_master_and_sensor_time_history_are_wide_absolute_tables(tmp_path: Path) -> None:
    case = next(case for case in dataset_cases() if case.name == "two_x_one_y_torsion")
    config = normalize_config(
        case.config
        | {
            "model": case.config["model"] | {"num_stories": 2},
            "stories": [{"story": 1}, {"story": 2}],
            "sensors": [
                sensor | {"story": 2}
                for sensor in case.config["sensors"]
            ],
            "ground_motion": {
                "dt": 0.02,
                "duration": 0.10,
                "synthetic": {"amplitude_x": 0.1, "amplitude_y": 0.05},
            },
        }
    )
    result = run(config)

    master_dir = tmp_path / "master"
    sensor_dir = tmp_path / "sensors"
    master_dir.mkdir()
    write_story3d_master_time_history(master_dir, result)
    map_sensors(
        case.config
        | {
            "model": case.config["model"] | {"num_stories": 2},
            "stories": [{"story": 1}, {"story": 2}],
            "sensors": [
                sensor | {"story": 2}
                for sensor in case.config["sensors"]
            ],
            "ground_motion": {
                "dt": 0.02,
                "duration": 0.10,
                "synthetic": {"amplitude_x": 0.1, "amplitude_y": 0.05},
            },
        },
        master_dir,
        sensor_dir,
    )

    master_acceleration = (master_dir / "acceleration.csv").read_text(encoding="utf-8").splitlines()
    acceleration = (sensor_dir / "acceleration.csv").read_text(encoding="utf-8").splitlines()
    assert master_acceleration[0].startswith("time,story_01_x,story_01_y,story_01_rz")
    assert acceleration[0] == (
        "time,01f_x_yneg,01f_x_ypos,01f_y_xpos,03f_x_yneg,03f_x_ypos,"
        "03f_y_xpos,07f_x_yneg,07f_x_ypos,07f_y_xpos,11f_x_yneg,11f_x_ypos,"
        "11f_y_xpos,16f_x_yneg,16f_x_ypos,16f_y_xpos"
    )
    assert len(acceleration) == 7


def test_sensor_remapping_uses_story_specific_mass_center(tmp_path: Path) -> None:
    raw = _base_raw(num_stories=2)
    raw["stories"] = [
        {"story": 1},
        {"story": 2, "mass_center": [1.0, 0.0]},
    ]
    raw["sensors"] = [
        {"id": "story2_y", "story": 2, "x": 1.0, "y": 0.0, "direction": "Y"},
    ]
    master_dir = tmp_path / "master"
    sensor_dir = tmp_path / "sensors"
    master_dir.mkdir()
    header = "time,story_01_x,story_01_y,story_01_rz,story_02_x,story_02_y,story_02_rz\n"
    body = "0.0,0.0,0.0,0.0,10.0,20.0,0.5\n"
    for quantity in ("acceleration", "velocity", "displacement"):
        (master_dir / f"{quantity}.csv").write_text(header + body, encoding="utf-8")

    map_sensors(raw, master_dir, sensor_dir)

    acceleration = (sensor_dir / "acceleration.csv").read_text(encoding="utf-8").splitlines()
    assert acceleration == ["time,story2_y", "0.0,20.0"]


def test_opensees_element_ids_allow_reordered_stories_and_reject_coordinate_jumps() -> None:
    from qrest_model.backends.opensees_story import _validate_opensees_element_connectivity

    raw = _base_raw(num_stories=2)
    raw["stories"] = [
        {"story": 1},
        {
            "story": 2,
            "elements": [
                {"id": "corner_se", "x": 5.0, "y": -3.0, "kx": 2.0e8, "ky": 2.0e8},
                {"id": "corner_sw", "x": -5.0, "y": -3.0, "kx": 2.0e8, "ky": 2.0e8},
                {"id": "corner_nw", "x": -5.0, "y": 3.0, "kx": 2.0e8, "ky": 2.0e8},
                {"id": "corner_ne", "x": 5.0, "y": 3.0, "kx": 2.0e8, "ky": 2.0e8},
            ],
        },
    ]
    _validate_opensees_element_connectivity(normalize_config(raw))

    raw["stories"][1]["elements"][0]["x"] = 5.1
    with pytest.raises(ValueError, match="matching x/y coordinates"):
        _validate_opensees_element_connectivity(normalize_config(raw))


def test_structural_properties_are_written_for_generated_cases(tmp_path: Path) -> None:
    base_case = next(case for case in dataset_cases() if case.name == "two_x_one_y_torsion")
    raw_config = base_case.config | {
        "model": base_case.config["model"] | {"num_stories": 2},
        "stories": [{"story": 1}, {"story": 2}],
        "sensors": [
            sensor | {"story": 2}
            for sensor in base_case.config["sensors"]
        ],
        "ground_motion": {
            "dt": 0.02,
            "duration": 0.10,
            "synthetic": {"amplitude_x": 0.1, "amplitude_y": 0.05},
        },
    }
    case = DatasetCase(
        name="mini_structural_case",
        data_type="mini",
        model_type="story3d",
        config=raw_config,
        description="mini",
    )
    result = run(normalize_config(raw_config))

    write_structural_properties(case, tmp_path / "structural_properties", result)

    output = tmp_path / "structural_properties"
    assert (output / "mass_matrix.csv").exists()
    assert (output / "stiffness_matrix.csv").exists()
    assert (output / "damping_matrix.csv").exists()
    assert (output / "modal_frequencies.csv").exists()
    assert (output / "mode_shapes.csv").exists()
    assert (output / "story_stiffness.csv").exists()
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["dof_count"] == 6
    assert summary["mode_count"] == 6
    assert summary["fundamental_frequency_hz"] > 0.0
    frequency_header = (output / "modal_frequencies.csv").read_text(encoding="utf-8").splitlines()[0]
    mode_shape_header = (output / "mode_shapes.csv").read_text(encoding="utf-8").splitlines()[0]
    assert frequency_header == "mode,circular_frequency_rad_s,frequency_hz,period_s"
    assert mode_shape_header.startswith("dof,mode_01,mode_02")


def test_generated_algorithm_configs_follow_model_properties(tmp_path: Path) -> None:
    base_case = next(case for case in dataset_cases() if case.name == "two_x_one_y_torsion")
    raw_config = base_case.config | {
        "model": base_case.config["model"] | {"num_stories": 2},
        "stories": [{"story": 1}, {"story": 2}],
        "sensors": [
            sensor | {"story": 2}
            for sensor in base_case.config["sensors"]
        ],
        "ground_motion": {
            "dt": 0.02,
            "duration": 0.10,
            "synthetic": {"amplitude_x": 0.1, "amplitude_y": 0.05},
        },
    }
    case = DatasetCase(
        name="mini_algorithm_config_case",
        data_type="mini",
        model_type="story3d",
        config=raw_config,
        description="mini",
    )
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    (dataset_dir / "config.json").write_text(json.dumps(raw_config), encoding="utf-8")
    result = run(normalize_config(raw_config))
    write_structural_properties(case, dataset_dir / "structural_properties", result)
    metadata = build_qrest_metadata(raw_config, npts=6, project_name="mini")
    (dataset_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    write_algorithm_configs(dataset_dir)

    rr_config = json.loads((dataset_dir / "config/rr/MappingIntegral.json").read_text(encoding="utf-8"))
    oma_config = json.loads((dataset_dir / "config/oma/FrequencyDomainDecomposition.json").read_text(encoding="utf-8"))
    ssi_cov_config = json.loads((dataset_dir / "config/oma/SSICOV.json").read_text(encoding="utf-8"))
    max_edp_config = json.loads((dataset_dir / "config/edp/MaxEDP.json").read_text(encoding="utf-8"))
    im_config = json.loads((dataset_dir / "config/im/IntensityMeasures.json").read_text(encoding="utf-8"))
    modal_rows = (dataset_dir / "structural_properties/modal_frequencies.csv").read_text(encoding="utf-8").splitlines()
    first_frequency = float(modal_rows[1].split(",")[2])
    first_period = float(modal_rows[1].split(",")[3])

    assert rr_config["fc_low"] == round(max(0.02, min(0.10, 0.12 * first_frequency)), 6)
    assert rr_config["fc_high"] == 20.0
    assert oma_config["nfft"] == 4
    assert oma_config["init_frequencies"][0][0] == round(first_frequency, 6)
    assert ssi_cov_config["Nmin"] == 2
    assert ssi_cov_config["Nmax"] == 30
    assert ssi_cov_config["frequency_band"] == [0.2, 5.0]
    assert max_edp_config["column_position"] == [
        [-5.0, -3.0],
        [-5.0, 0.0],
        [-5.0, 3.0],
        [0.0, -3.0],
        [0.0, 0.0],
        [0.0, 3.0],
        [5.0, -3.0],
        [5.0, 0.0],
        [5.0, 3.0],
    ]
    assert im_config["response_spectrum_ti"]["period_ti"] == round(first_period, 6)


def test_sensor_node_validation_accepts_rigid_mapping_result() -> None:
    case = next(case for case in dataset_cases() if case.name == "two_x_one_y_torsion")
    raw = case.config | {
        "model": case.config["model"] | {"num_stories": 2},
        "stories": [{"story": 1}, {"story": 2}],
        "sensors": [
            sensor | {"story": 2}
            for sensor in case.config["sensors"]
        ],
        "ground_motion": {
            "dt": 0.02,
            "duration": 0.10,
            "synthetic": {"amplitude_x": 0.1, "amplitude_y": 0.05},
        },
    }
    config = normalize_config(raw)
    result = run(config)
    result["sensor_displacement"] = tuple(
        map_floor_motion(result["displacement"][:, sensor.story - 1, :], sensor.x, sensor.y)
        for sensor in config.sensors
    )
    result["sensor_velocity"] = tuple(
        map_floor_motion(result["velocity"][:, sensor.story - 1, :], sensor.x, sensor.y)
        for sensor in config.sensors
    )
    result["sensor_acceleration"] = tuple(
        map_floor_motion(result["acceleration"][:, sensor.story - 1, :], sensor.x, sensor.y)
        for sensor in config.sensors
    )

    metrics = validate_opensees_sensor_nodes(raw, result)

    assert metrics["sensor_node_disp_max_abs"] == 0.0
    assert metrics["sensor_node_vel_max_abs"] == 0.0
    assert metrics["sensor_node_acc_max_abs"] == 0.0


def test_qrest_metadata_generation_matches_model_sensors() -> None:
    if Metadata is None:
        pytest.skip("py_algorithm is required to validate qREST metadata parsing.")
    case = next(case for case in dataset_cases() if case.name == "two_x_one_y_torsion")
    metadata = build_qrest_metadata(case.config, npts=15000, project_name="test_project")
    parsed = Metadata.from_json(json.dumps(metadata))
    channels = metadata["InstrumentInfo"]["Channels"]

    assert metadata["Header"] == "qREST_DATA"
    assert metadata["BuildingInfo"]["ProjectName"] == "test_project"
    assert metadata["BuildingInfo"]["ElevationNum"] == 16
    assert metadata["DataInfo"]["DT"] == 0.02
    assert metadata["DataInfo"]["NPTS"] == 15000
    assert metadata["InstrumentInfo"]["ChannelNum"] == 15
    assert [channel["ChannelID"] for channel in channels[:3]] == [
        "01f_x_yneg",
        "01f_x_ypos",
        "01f_y_xpos",
    ]
    assert [channel["Azimuth"] for channel in channels[:3]] == [90.0, 90.0, 0.0]
    assert channels[0]["LocationXYZ"] == [0.0, -3.0, 0.0]
    assert channels[-1]["LocationXYZ"] == [5.0, 0.0, 45.0]
    assert parsed.ChannelNum == 15


def test_staggered_special_metadata_matches_requested_layout() -> None:
    if Metadata is None:
        pytest.skip("py_algorithm is required to validate qREST metadata parsing.")
    case = next(case for case in dataset_cases() if case.name == "staggered_2x_center_y")
    metadata = build_qrest_metadata(case.config, npts=15000, project_name="staggered_test")
    parsed = Metadata.from_json(json.dumps(metadata))
    channels = metadata["InstrumentInfo"]["Channels"]

    assert metadata["InstrumentInfo"]["ChannelNum"] == 15
    assert [channel["ChannelID"] for channel in channels[:10]] == [
        "01f_x_yneg",
        "01f_x_ypos",
        "03f_x_yneg",
        "03f_x_ypos",
        "07f_x_yneg",
        "07f_x_ypos",
        "11f_x_yneg",
        "11f_x_ypos",
        "16f_x_yneg",
        "16f_x_ypos",
    ]
    assert [channel["ChannelID"] for channel in channels[10:]] == [
        "01f_center_y",
        "04f_center_y",
        "08f_center_y",
        "12f_center_y",
        "16f_center_y",
    ]
    assert [channel["Azimuth"] for channel in channels[:10]] == [90.0] * 10
    assert [channel["Azimuth"] for channel in channels[10:]] == [0.0] * 5
    assert channels[0]["LocationXYZ"] == [0.0, -3.0, 0.0]
    assert channels[1]["LocationXYZ"] == [0.0, 3.0, 0.0]
    assert channels[10]["LocationXYZ"] == [0.0, 0.0, 0.0]
    assert channels[-1]["LocationXYZ"] == [0.0, 0.0, 45.0]
    assert parsed.ChannelNum == 15


def test_export_dataset_matches_metadata_channel_order(tmp_path: Path) -> None:
    generated_dir = tmp_path / "generated_case"
    time_history_dir = generated_dir / "time_history"
    time_history_dir.mkdir(parents=True)
    metadata = {
        "Header": "qREST_DATA",
        "Version": [1, 0, 0],
        "Units": ["m", "s"],
        "BuildingInfo": {
            "ProjectName": "test",
            "GeoLocation": {"Longitude": 0.0, "Latitude": 0.0, "NorthAngle": 0.0},
            "StructuralType": "NumericalModel",
            "StructuralFootprint": {
                "Shape": "Rectangular",
                "Parameters": {"Length": 10.0, "Width": 6.0},
                "BoundingBox": {"MaxX": 5.0, "MinX": -5.0, "MaxY": 3.0, "MinY": -3.0},
            },
            "ElevationNum": 1,
            "Elevation": [0.0],
        },
        "InstrumentInfo": {
            "Provider": "qREST_MODEL",
            "ChannelNum": 2,
            "Channels": [
                {"ChannelNo": 1, "ChannelID": "ch_b", "Measurand": "Acceleration", "Scale": 1, "Azimuth": 90.0, "LocationXYZ": [0, 0, 0]},
                {"ChannelNo": 2, "ChannelID": "ch_a", "Measurand": "Acceleration", "Scale": 1, "Azimuth": 0.0, "LocationXYZ": [0, 0, 0]},
            ],
        },
        "DataInfo": {
            "EventName": "test",
            "StartTime": "1970-01-01T00:00:00.000+00:00",
            "NPTS": 2,
            "DT": 0.02,
            "Corrected": "MODEL_ABSOLUTE_RESPONSE",
        },
    }
    (generated_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    (time_history_dir / "acceleration.csv").write_text(
        "time,ch_a,ch_b\n0.0,1.0,2.0\n0.02,3.0,4.0\n",
        encoding="utf-8",
    )

    exported = export_dataset(
        generated_dir,
        tmp_path / "qrest_case",
        config_source=None,
    )

    assert (exported / "qrest_case_metadata.json").exists()
    assert (exported / "qrest_case_data.txt").read_text(encoding="utf-8") == (
        "2.0 1.0\n4.0 3.0\n"
    )


def test_opensees_matches_direct_for_simple_damped_no_torsion_case(tmp_path: Path) -> None:
    if os.environ.get("QREST_RUN_OPENSEES_TESTS") != "1":
        pytest.skip("Set QREST_RUN_OPENSEES_TESTS=1 to run OpenSeesPy validation.")

    from qrest_model.backends.opensees_story import run as run_opensees

    raw = _base_raw(num_stories=1)
    ax_path = tmp_path / "nonzero_initial_ax.txt"
    np.savetxt(ax_path, np.linspace(0.12, -0.08, 11))
    raw["sensors"] = []
    raw["damping"] = {"type": "rayleigh", "zeta": 0.02, "modes": [1, 3]}
    raw["ground_motion"] = {
        "dt": 0.02,
        "duration": 0.2,
        "ax_file": str(ax_path),
    }
    config = normalize_config(raw)
    direct = run(config)
    opensees = run_opensees(config)

    for key in ("displacement", "velocity", "acceleration", "absolute_acceleration"):
        assert np.max(np.abs(direct[key] - opensees[key])) < 1.0e-12
