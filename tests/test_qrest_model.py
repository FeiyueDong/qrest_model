from __future__ import annotations
import json
import os

from qrest_model.analysis.linear_system import LinearSystem
from qrest_model.analysis.modal import modal_analysis
from qrest_model.analysis.newmark import NewmarkSolver
from qrest_model.analysis.result import AnalysisMetadata, AnalysisResult, ResponseHistory
from qrest_model.backends.base import DirectBackend, run_analysis
from qrest_model.cli import main as cli_main
from qrest_model.common.compare import compare_master_arrays, symmetric_relative_l2
from qrest_model.theory.euler_beam import assemble_matrices as assemble_euler_matrices
from qrest_model.theory.euler_beam import base_excitation_influence as euler_base_excitation_influence
from qrest_model.theory.euler_beam import element_mass as euler_element_mass
from qrest_model.theory.euler_beam import element_stiffness as euler_element_stiffness
from qrest_model.theory.rayleigh_beam import assemble_matrices as assemble_rayleigh_matrices
from qrest_model.theory.rayleigh_beam import base_excitation_influence as rayleigh_base_excitation_influence
from qrest_model.theory.shear_flexure import assemble_matrices as assemble_shear_flexure_matrices
from qrest_model.theory.shear_flexure import element_stiffness as shear_flexure_element_stiffness
from qrest_model.theory.shear_flexure import shear_element_stiffness
from qrest_model.theory.timoshenko_beam import assemble_matrices as assemble_timoshenko_matrices
from qrest_model.theory.timoshenko_beam import element_mass as timoshenko_element_mass
from qrest_model.theory.timoshenko_beam import element_stiffness as timoshenko_element_stiffness
from qrest_model.theory.story_stiffness import story_stiffness
from qrest_model.theory.shear_stiffness import assemble_shear_stiffness
from qrest_model.postprocess import map_floor_motion, map_sensors
from qrest_model.schema import (
    load_shear_config,
    normalize_euler_config,
    normalize_rayleigh_config,
    normalize_shear_config,
    normalize_shear_flexure_config,
    normalize_timoshenko_config,
)
from qrest_model.common.ground_motion import load_ground_motion
from qrest_model.schema import load_config, normalize_config
from qrest_model.datasets.cases import DATASET_CONFIG_ROOT, DatasetCase, dataset_cases
from qrest_model.datasets.validation import validate_opensees_sensor_nodes
from qrest_model.exporters.algorithm_config import write_algorithm_configs
from qrest_model.exporters.qrest_dataset import export_dataset
from qrest_model.exporters.qrest_metadata import build_qrest_metadata
from qrest_model.exporters.structural_properties import write_structural_properties
from qrest_model.exporters.time_history import write_story3d_master_time_history
from qrest_model.backends.direct_shear import run as run_direct_shear
from qrest_model.backends.direct_shear import run_result as run_direct_shear_result
from qrest_model.backends.direct_stiffness import run
from qrest_model.backends.direct_stiffness import run_result as run_direct_stiffness_result
from scripts import build_datasets as legacy_build_datasets
from scripts import export_datasets as legacy_export_datasets
from scripts import make_algorithm_configs as legacy_algorithm_configs
from scripts import make_metadata as legacy_metadata
from scripts import map_sensors as legacy_map_sensors
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
REFERENCE_ROOT = MODEL_ROOT / "tests" / "reference"


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


def _golden_rigid_raw() -> dict:
    raw = _base_raw(num_stories=3)
    raw["sensors"] = [{"id": "roof_x", "story": 3, "x": 5.0, "y": 3.0, "direction": "X"}]
    raw["ground_motion"] = {
        "dt": 0.01,
        "duration": 0.1,
        "synthetic": {"amplitude_x": 0.12, "amplitude_y": 0.0, "frequency_x": 1.0},
    }
    return raw


def _golden_shear_raw() -> dict:
    return {
        "schema_version": "2.0",
        "model": {"type": "shear_building_1d", "num_stories": 3, "dof_per_floor": ["Ux"]},
        "floor_defaults": {"mass": 1.0e6, "stiffness": 8.0e8},
        "stories": [{"story": 1}, {"story": 2}, {"story": 3}],
        "sensors": [{"id": "roof_accel", "story": 3, "quantity": "accel"}],
        "damping": {"type": "rayleigh", "zeta": 0.02, "modes": [1, 2]},
        "ground_motion": {
            "dt": 0.01,
            "duration": 0.1,
            "synthetic": {"amplitude_x": 0.1, "amplitude_y": 0.0, "frequency_x": 1.0},
        },
    }


def _golden_rigid_eccentric_raw() -> dict:
    raw = _base_raw(num_stories=3)
    raw["floor_defaults"] = raw["floor_defaults"] | {
        "mass_center": [0.2, -0.1],
    }
    raw["stories"] = [
        {"story": 1},
        {"story": 2, "mass_center": [0.35, -0.05]},
        {"story": 3, "mass_center": [0.5, 0.0]},
    ]
    raw["sensors"] = [
        {"id": "roof_x_ypos", "story": 3, "x": 5.0, "y": 3.0, "direction": "X"},
        {"id": "roof_y_xneg", "story": 3, "x": -5.0, "y": 0.0, "direction": "Y"},
        {"id": "roof_rz", "story": 3, "x": 0.0, "y": 0.0, "direction": "RZ"},
    ]
    raw["ground_motion"] = {
        "dt": 0.01,
        "duration": 0.1,
        "synthetic": {
            "amplitude_x": 0.12,
            "amplitude_y": 0.04,
            "frequency_x": 1.0,
            "frequency_y": 1.4,
        },
    }
    return raw


def _euler_raw(num_stories: int = 3) -> dict:
    return {
        "schema_version": "2.0",
        "model": {
            "type": "euler_beam_2d",
            "num_stories": num_stories,
            "dof_per_floor": ["U", "Theta"],
        },
        "geometry": {"story_heights": [3.0 for _ in range(num_stories)]},
        "section_defaults": {
            "E": 3.0e10,
            "A": 20.0,
            "I": 90.0,
            "density": 2500.0,
        },
        "sections": [{"story": i + 1} for i in range(num_stories)],
        "sensors": [
            {"id": "roof_u", "story": num_stories, "dof": "U", "quantity": "accel"},
            {"id": "roof_theta", "story": num_stories, "dof": "Theta", "quantity": "disp"},
        ],
        "damping": {"type": "rayleigh", "zeta": 0.02, "modes": [1, 2]},
        "ground_motion": {
            "dt": 0.01,
            "duration": 0.1,
            "synthetic": {"amplitude_x": 0.1, "amplitude_y": 0.0, "frequency_x": 1.0},
        },
    }


def _rayleigh_raw(num_stories: int = 3, rotational_inertia: float = 2.0e5) -> dict:
    raw = _euler_raw(num_stories)
    raw["model"] = raw["model"] | {"type": "rayleigh_beam_2d"}
    raw["section_defaults"] = raw["section_defaults"] | {
        "rotational_inertia": rotational_inertia,
    }
    return raw


def _timoshenko_raw(num_stories: int = 3, *, G: float = 1.25e10, shear_area: float = 16.0) -> dict:
    raw = _euler_raw(num_stories)
    raw["model"] = raw["model"] | {"type": "timoshenko_beam_2d"}
    raw["section_defaults"] = raw["section_defaults"] | {
        "G": G,
        "shear_area": shear_area,
    }
    return raw


def _shear_flexure_raw(num_stories: int = 3, *, shear_stiffness: float = 8.0e8) -> dict:
    raw = _euler_raw(num_stories)
    raw["model"] = raw["model"] | {"type": "shear_flexure_building_2d"}
    raw["story_defaults"] = {"shear_stiffness": shear_stiffness}
    raw["stories"] = [{"story": i + 1} for i in range(num_stories)]
    raw.pop("sections")
    return raw


def _analysis_signature(result: AnalysisResult) -> dict:
    flat_disp = result.relative.displacement.reshape(result.time.size, -1)
    flat_acc = result.relative.acceleration.reshape(result.time.size, -1)
    indices = [0, 5, 10]
    return {
        "frequency_hz": result.modal.frequency[: min(6, result.modal.frequency.size)],
        "peak_relative_displacement": np.max(np.abs(flat_disp), axis=0),
        "peak_relative_acceleration": np.max(np.abs(flat_acc), axis=0),
        "selected_indices": indices,
        "selected_relative_displacement": flat_disp[indices],
        "sensor_last_value": result.sensors.rows[-1]["value"],
        "sensor_last_relative_value": result.sensors.rows[-1]["relative_value"],
    }


def _assert_signature_matches(result: AnalysisResult, reference_name: str) -> None:
    reference = json.loads((REFERENCE_ROOT / reference_name).read_text(encoding="utf-8"))
    signature = _analysis_signature(result)
    assert signature["selected_indices"] == reference["selected_indices"]
    for key in (
        "frequency_hz",
        "peak_relative_displacement",
        "peak_relative_acceleration",
        "selected_relative_displacement",
    ):
        assert np.allclose(signature[key], np.asarray(reference[key]), rtol=1.0e-8, atol=1.0e-12)
    assert np.isclose(signature["sensor_last_value"], reference["sensor_last_value"], rtol=1.0e-8, atol=1.0e-12)
    assert np.isclose(
        signature["sensor_last_relative_value"],
        reference["sensor_last_relative_value"],
        rtol=1.0e-8,
        atol=1.0e-12,
    )


def _require_opensees_tests() -> None:
    if os.environ.get("QREST_RUN_OPENSEES_TESTS") != "1":
        pytest.skip("Set QREST_RUN_OPENSEES_TESTS=1 to run OpenSeesPy validation.")


def _assert_response_close(
    direct: AnalysisResult,
    opensees: AnalysisResult,
    *,
    displacement_atol: float = 1.0e-8,
    velocity_atol: float = 1.0e-7,
    acceleration_atol: float = 1.0e-6,
) -> None:
    assert np.allclose(direct.relative.displacement, opensees.relative.displacement, atol=displacement_atol, rtol=1.0e-7)
    assert np.allclose(direct.relative.velocity, opensees.relative.velocity, atol=velocity_atol, rtol=1.0e-7)
    assert np.allclose(direct.relative.acceleration, opensees.relative.acceleration, atol=acceleration_atol, rtol=1.0e-7)
    assert np.allclose(direct.absolute.acceleration, opensees.absolute.acceleration, atol=acceleration_atol, rtol=1.0e-7)


def _scaled_corner_elements(scale: float) -> list[dict]:
    return [
        {"id": "corner_sw", "x": -5.0, "y": -3.0, "kx": 2.0e8 * scale, "ky": 2.0e8 * scale},
        {"id": "corner_se", "x": 5.0, "y": -3.0, "kx": 2.0e8 * scale, "ky": 2.0e8 * scale},
        {"id": "corner_ne", "x": 5.0, "y": 3.0, "kx": 2.0e8 * scale, "ky": 2.0e8 * scale},
        {"id": "corner_nw", "x": -5.0, "y": 3.0, "kx": 2.0e8 * scale, "ky": 2.0e8 * scale},
    ]


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
    assert result.modal is not None
    assert result.modal.frequency.size == 6


def test_rigid_symmetric_golden_regression_signature() -> None:
    _assert_signature_matches(
        run_analysis(_golden_rigid_raw(), backend="direct"),
        "rigid_symmetric_3story.json",
    )


def test_rigid_eccentric_golden_regression_signature() -> None:
    _assert_signature_matches(
        run_analysis(_golden_rigid_eccentric_raw(), backend="direct"),
        "rigid_eccentric_3story.json",
    )


def test_euler_element_matrices_match_classic_consistent_forms() -> None:
    stiffness = euler_element_stiffness(E=2.0, I=3.0, length=4.0)
    mass = euler_element_mass(density=5.0, area=6.0, length=4.0)

    assert np.allclose(stiffness, stiffness.T)
    assert np.allclose(mass, mass.T)
    assert np.allclose(
        stiffness,
        6.0 / 64.0 * np.array(
            [
                [12.0, 24.0, -12.0, 24.0],
                [24.0, 64.0, -24.0, 32.0],
                [-12.0, -24.0, 12.0, -24.0],
                [24.0, 32.0, -24.0, 64.0],
            ]
        ),
    )
    assert np.all(np.linalg.eigvalsh(mass) > 0.0)


def test_euler_beam_assembly_uses_fixed_base_and_ground_influence() -> None:
    config = normalize_euler_config(_euler_raw(num_stories=2))
    mass, stiffness = assemble_euler_matrices(config.sections, config.geometry)

    assert mass.shape == (4, 4)
    assert stiffness.shape == (4, 4)
    assert np.all(np.linalg.eigvalsh(mass) > 0.0)
    assert np.all(np.linalg.eigvalsh(stiffness) > 0.0)
    influence = euler_base_excitation_influence(config.sections, config.geometry)
    assert influence.shape == (4,)
    assert np.all(np.isfinite(influence))
    assert not np.allclose(influence, [1.0, 0.0, 1.0, 0.0])
    assert np.any(np.abs(influence[1::2]) > 0.0)


def test_euler_schema_and_direct_backend_run_through_unified_entry() -> None:
    config = normalize_euler_config(_euler_raw(num_stories=3))
    result = run_analysis(config, backend="direct")

    assert config.geometry.elevations == (3.0, 6.0, 9.0)
    assert result.metadata.backend == "direct_euler"
    assert result.relative.displacement.shape == (11, 3, 2)
    assert result.absolute is not None
    assert result.ground is not None
    assert result.modal is not None
    assert result.modal.frequency.size == 6
    assert len(result.sensors.rows) == 22
    assert np.allclose(
        result.absolute.acceleration[:, :, 0],
        result.relative.acceleration[:, :, 0] + result.ground.acceleration[:, 0, None],
    )
    assert np.allclose(result.absolute.acceleration[:, :, 1], result.relative.acceleration[:, :, 1])


def test_euler_schema_rejects_rz_alias_for_bending_rotation() -> None:
    raw = _euler_raw(num_stories=1)
    raw["sensors"] = [{"id": "bad", "story": 1, "dof": "Rz"}]

    with pytest.raises(ValueError, match="not rigid-floor Rz"):
        normalize_euler_config(raw)


def test_euler_golden_regression_signature() -> None:
    _assert_signature_matches(
        run_analysis(_euler_raw(num_stories=3), backend="direct"),
        "euler_3story.json",
    )


def test_rayleigh_beam_mass_adds_nodal_rotary_inertia() -> None:
    euler = normalize_euler_config(_euler_raw(num_stories=2))
    rayleigh = normalize_rayleigh_config(_rayleigh_raw(num_stories=2, rotational_inertia=2.5e5))
    euler_mass, euler_stiffness = assemble_euler_matrices(euler.sections, euler.geometry)
    rayleigh_mass, rayleigh_stiffness = assemble_rayleigh_matrices(rayleigh.sections, rayleigh.geometry)

    expected_extra = np.diag([0.0, 2.5e5, 0.0, 2.5e5])
    assert np.allclose(rayleigh_stiffness, euler_stiffness)
    assert np.allclose(rayleigh_mass, euler_mass + expected_extra)
    assert not np.allclose(
        rayleigh_base_excitation_influence(rayleigh.sections, rayleigh.geometry),
        euler_base_excitation_influence(euler.sections, euler.geometry),
    )


def test_rayleigh_degenerates_to_euler_when_rotary_inertia_is_zero() -> None:
    euler = run_analysis(_euler_raw(num_stories=3), backend="direct")
    rayleigh = run_analysis(_rayleigh_raw(num_stories=3, rotational_inertia=0.0), backend="direct")

    assert np.allclose(rayleigh.mass_matrix, euler.mass_matrix)
    assert np.allclose(rayleigh.stiffness_matrix, euler.stiffness_matrix)
    assert np.allclose(rayleigh.modal.frequency, euler.modal.frequency)
    assert np.allclose(rayleigh.relative.displacement, euler.relative.displacement)


def test_rayleigh_schema_and_direct_backend_run_through_unified_entry() -> None:
    config = normalize_rayleigh_config(_rayleigh_raw(num_stories=3, rotational_inertia=2.0e5))
    result = run_analysis(config, backend="direct")

    assert all(section.rotational_inertia == 2.0e5 for section in config.sections)
    assert result.metadata.backend == "direct_rayleigh"
    assert result.relative.displacement.shape == (11, 3, 2)
    assert result.modal is not None
    assert len(result.sensors.rows) == 22
    assert np.all(np.diag(result.mass_matrix)[1::2] > np.diag(run_analysis(_euler_raw(3), backend="direct").mass_matrix)[1::2])


def test_rayleigh_schema_rejects_negative_rotary_inertia() -> None:
    raw = _rayleigh_raw(num_stories=1, rotational_inertia=-1.0)

    with pytest.raises(ValueError, match="rotational_inertia must be non-negative"):
        normalize_rayleigh_config(raw)


def test_euler_schema_rejects_rotary_inertia() -> None:
    raw = _euler_raw(num_stories=1)
    raw["section_defaults"] = raw["section_defaults"] | {"rotational_inertia": 1.0}

    with pytest.raises(ValueError, match="use rayleigh_beam_2d"):
        normalize_euler_config(raw)


def test_rayleigh_golden_regression_signature() -> None:
    _assert_signature_matches(
        run_analysis(_rayleigh_raw(num_stories=3), backend="direct"),
        "rayleigh_3story.json",
    )


def test_timoshenko_element_stiffness_matches_standard_form_and_euler_limit() -> None:
    stiffness = timoshenko_element_stiffness(E=2.0, G=4.0, area=5.0, shear_area=6.0, I=3.0, length=4.0)

    phi = 12.0 * 2.0 * 3.0 / (4.0 * 6.0 * 4.0**2)
    expected = 2.0 * 3.0 / (4.0**3 * (1.0 + phi)) * np.array(
        [
            [12.0, 24.0, -12.0, 24.0],
            [24.0, (4.0 + phi) * 16.0, -24.0, (2.0 - phi) * 16.0],
            [-12.0, -24.0, 12.0, -24.0],
            [24.0, (2.0 - phi) * 16.0, -24.0, (4.0 + phi) * 16.0],
        ]
    )
    euler_limit = timoshenko_element_stiffness(E=2.0, G=1.0e20, area=5.0, shear_area=6.0, I=3.0, length=4.0)

    assert np.allclose(stiffness, stiffness.T)
    assert np.allclose(stiffness, expected)
    assert np.allclose(euler_limit, euler_element_stiffness(E=2.0, I=3.0, length=4.0), rtol=1.0e-12, atol=1.0e-12)


def test_timoshenko_element_mass_matches_explicit_consistent_form() -> None:
    mass = timoshenko_element_mass(E=2.0, G=4.0, area=5.0, shear_area=6.0, I=3.0, density=7.0, length=4.0)

    phi = 12.0 * 2.0 * 3.0 / (4.0 * 6.0 * 4.0**2)
    mass_per_length = 7.0 * 5.0
    c1z = mass_per_length * 4.0 / (210.0 * (1.0 + phi) ** 2)
    translational = c1z * np.array(
        [
            [70.0 * phi**2 + 147.0 * phi + 78.0, 35.0 * phi**2 + 77.0 * phi + 44.0, 35.0 * phi**2 + 63.0 * phi + 27.0, -(35.0 * phi**2 + 63.0 * phi + 26.0)],
            [35.0 * phi**2 + 77.0 * phi + 44.0, 4.0 * (7.0 * phi**2 + 14.0 * phi + 8.0), 35.0 * phi**2 + 63.0 * phi + 26.0, -4.0 * (7.0 * phi**2 + 14.0 * phi + 6.0)],
            [35.0 * phi**2 + 63.0 * phi + 27.0, 35.0 * phi**2 + 63.0 * phi + 26.0, 70.0 * phi**2 + 147.0 * phi + 78.0, -(35.0 * phi**2 + 77.0 * phi + 44.0)],
            [-(35.0 * phi**2 + 63.0 * phi + 26.0), -4.0 * (7.0 * phi**2 + 14.0 * phi + 6.0), -(35.0 * phi**2 + 77.0 * phi + 44.0), 4.0 * (7.0 * phi**2 + 14.0 * phi + 8.0)],
        ]
    )
    c2z = 7.0 * 3.0 / (30.0 * 4.0 * (1.0 + phi) ** 2)
    rotary = c2z * np.array(
        [
            [36.0, -4.0 * (15.0 * phi - 3.0), -36.0, -4.0 * (15.0 * phi - 3.0)],
            [-4.0 * (15.0 * phi - 3.0), 16.0 * (10.0 * phi**2 + 5.0 * phi + 4.0), 4.0 * (15.0 * phi - 3.0), 16.0 * (5.0 * phi**2 - 5.0 * phi - 1.0)],
            [-36.0, 4.0 * (15.0 * phi - 3.0), 36.0, 4.0 * (15.0 * phi - 3.0)],
            [-4.0 * (15.0 * phi - 3.0), 16.0 * (5.0 * phi**2 - 5.0 * phi - 1.0), 4.0 * (15.0 * phi - 3.0), 16.0 * (10.0 * phi**2 + 5.0 * phi + 4.0)],
        ]
    )

    assert np.allclose(mass, mass.T)
    assert np.allclose(mass, translational + rotary)

    euler_like = timoshenko_element_mass(
        E=3.0e10,
        G=1.0e20,
        area=1.0e12,
        shear_area=1.0e12,
        I=90.0,
        density=5.0e-8,
        length=3.0,
    )
    assert np.allclose(euler_like, euler_element_mass(density=5.0e-8, area=1.0e12, length=3.0), rtol=1.0e-8, atol=1.0e-8)


def test_timoshenko_degenerates_to_euler_for_large_shear_stiffness() -> None:
    euler_raw = _euler_raw(num_stories=3)
    timoshenko_raw = _timoshenko_raw(num_stories=3, G=1.0e20, shear_area=1.0e12)
    for raw in (euler_raw, timoshenko_raw):
        raw["section_defaults"] = raw["section_defaults"] | {
            "A": 1.0e12,
            "density": 5.0e-8,
        }
    euler_config = normalize_euler_config(euler_raw)
    timoshenko_config = normalize_timoshenko_config(timoshenko_raw)
    euler_mass, euler_stiffness = assemble_euler_matrices(euler_config.sections, euler_config.geometry)
    timoshenko_mass, timoshenko_stiffness = assemble_timoshenko_matrices(
        timoshenko_config.sections,
        timoshenko_config.geometry,
    )

    assert np.allclose(timoshenko_mass, euler_mass, rtol=1.0e-8, atol=1.0e-6)
    assert np.allclose(timoshenko_stiffness, euler_stiffness, rtol=1.0e-8, atol=1.0e-6)

    euler = run_analysis(euler_raw, backend="direct")
    timoshenko = run_analysis(timoshenko_raw, backend="direct")

    assert np.allclose(timoshenko.modal.frequency, euler.modal.frequency, rtol=1.0e-8, atol=1.0e-8)
    assert np.allclose(timoshenko.relative.displacement, euler.relative.displacement, rtol=1.0e-8, atol=1.0e-12)


def test_timoshenko_schema_and_direct_backend_run_through_unified_entry() -> None:
    config = normalize_timoshenko_config(_timoshenko_raw(num_stories=3))
    result = run_analysis(config, backend="direct")

    assert all(section.G == 1.25e10 and section.shear_area == 16.0 for section in config.sections)
    assert result.metadata.backend == "direct_timoshenko"
    assert result.relative.displacement.shape == (11, 3, 2)
    assert result.modal is not None
    assert len(result.sensors.rows) == 22


def test_timoshenko_schema_rejects_missing_or_negative_shear_contract() -> None:
    raw = _timoshenko_raw(num_stories=1)
    del raw["section_defaults"]["G"]
    with pytest.raises(ValueError, match="requires G"):
        normalize_timoshenko_config(raw)

    raw = _timoshenko_raw(num_stories=1, shear_area=-1.0)
    with pytest.raises(ValueError, match="G and shear_area must be positive"):
        normalize_timoshenko_config(raw)


def test_timoshenko_golden_regression_signature() -> None:
    _assert_signature_matches(
        run_analysis(_timoshenko_raw(num_stories=3), backend="direct"),
        "timoshenko_3story.json",
    )


def test_cli_run_writes_timoshenko_backend_outputs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    case_path = tmp_path / "timoshenko.json"
    case_path.write_text(json.dumps(_timoshenko_raw(num_stories=2)), encoding="utf-8")
    output = tmp_path / "run_output"

    exit_code = cli_main([
        "run",
        str(case_path),
        "--backend",
        "direct",
        "--output",
        str(output),
    ])

    assert exit_code == 0
    assert (output / "master_response.csv").exists()
    assert (output / "sensor_response.csv").exists()
    header = (output / "master_response.csv").read_text(encoding="utf-8").splitlines()[0]
    assert "theta" in header
    assert str(output) in capsys.readouterr().out


def test_cli_run_writes_rayleigh_backend_outputs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    case_path = tmp_path / "rayleigh.json"
    case_path.write_text(json.dumps(_rayleigh_raw(num_stories=2)), encoding="utf-8")
    output = tmp_path / "run_output"

    exit_code = cli_main([
        "run",
        str(case_path),
        "--backend",
        "direct",
        "--output",
        str(output),
    ])

    assert exit_code == 0
    assert (output / "master_response.csv").exists()
    assert (output / "sensor_response.csv").exists()
    header = (output / "master_response.csv").read_text(encoding="utf-8").splitlines()[0]
    assert "theta" in header
    assert str(output) in capsys.readouterr().out


def test_cli_run_writes_euler_backend_outputs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    case_path = tmp_path / "euler.json"
    case_path.write_text(json.dumps(_euler_raw(num_stories=2)), encoding="utf-8")
    output = tmp_path / "run_output"

    exit_code = cli_main([
        "run",
        str(case_path),
        "--backend",
        "direct",
        "--output",
        str(output),
    ])

    assert exit_code == 0
    assert (output / "master_response.csv").exists()
    assert (output / "sensor_response.csv").exists()
    header = (output / "master_response.csv").read_text(encoding="utf-8").splitlines()[0]
    assert "theta" in header
    assert str(output) in capsys.readouterr().out


def test_shear_flexure_element_stiffness_combines_flexural_and_shear_branches() -> None:
    stiffness = shear_flexure_element_stiffness(E=2.0, I=3.0, length=4.0, shear_stiffness=5.0)
    shear = shear_element_stiffness(5.0)

    expected_shear = 5.0 * np.array(
        [
            [1.0, 0.0, -1.0, 0.0],
            [0.0, 0.0, 0.0, 0.0],
            [-1.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 0.0],
        ]
    )
    expected = euler_element_stiffness(E=2.0, I=3.0, length=4.0) + expected_shear

    assert np.allclose(shear, expected_shear)
    assert np.allclose(stiffness, stiffness.T)
    assert np.allclose(stiffness, expected)


def test_shear_flexure_degenerates_to_flexural_branch_when_shear_stiffness_is_zero() -> None:
    euler_config = normalize_euler_config(_euler_raw(num_stories=3))
    shear_flexure_config = normalize_shear_flexure_config(_shear_flexure_raw(num_stories=3, shear_stiffness=0.0))
    euler_mass, euler_stiffness = assemble_euler_matrices(euler_config.sections, euler_config.geometry)
    shear_flexure_mass, shear_flexure_stiffness = assemble_shear_flexure_matrices(
        shear_flexure_config.stories,
        shear_flexure_config.geometry,
    )

    assert np.allclose(shear_flexure_mass, euler_mass)
    assert np.allclose(shear_flexure_stiffness, euler_stiffness)

    euler = run_analysis(_euler_raw(num_stories=3), backend="direct")
    shear_flexure = run_analysis(_shear_flexure_raw(num_stories=3, shear_stiffness=0.0), backend="direct")

    assert np.allclose(shear_flexure.modal.frequency, euler.modal.frequency, rtol=1.0e-12, atol=1.0e-12)
    assert np.allclose(shear_flexure.relative.displacement, euler.relative.displacement, rtol=1.0e-12, atol=1.0e-14)


def test_shear_flexure_frequency_increases_with_shear_branch_stiffness() -> None:
    flexural = run_analysis(_shear_flexure_raw(num_stories=3, shear_stiffness=0.0), backend="direct")
    mixed = run_analysis(_shear_flexure_raw(num_stories=3, shear_stiffness=8.0e8), backend="direct")
    stiff_shear = run_analysis(_shear_flexure_raw(num_stories=3, shear_stiffness=8.0e9), backend="direct")

    assert mixed.modal.frequency[0] > flexural.modal.frequency[0]
    assert stiff_shear.modal.frequency[0] > mixed.modal.frequency[0]


def test_shear_flexure_schema_and_direct_backend_run_through_unified_entry() -> None:
    raw = _shear_flexure_raw(num_stories=3)
    raw["stories"] = [
        {"story": 1, "flexural_section": {"I": 110.0}, "shear_stiffness": 7.0e8},
        {"story": 2, "flexural_section": {"I": 90.0}, "shear_stiffness": 8.0e8},
        {"story": 3, "flexural_section": {"I": 70.0, "density": 2400.0}, "shear_stiffness": 9.0e8},
    ]
    config = normalize_shear_flexure_config(raw)
    result = run_analysis(config, backend="direct")

    assert [story.shear_stiffness for story in config.stories] == [7.0e8, 8.0e8, 9.0e8]
    assert [story.flexural_section.I for story in config.stories] == [110.0, 90.0, 70.0]
    assert result.metadata.backend == "direct_shear_flexure"
    assert result.relative.displacement.shape == (11, 3, 2)
    assert result.modal is not None
    assert len(result.sensors.rows) == 22


def test_shear_flexure_schema_rejects_missing_or_negative_shear_branch() -> None:
    raw = _shear_flexure_raw(num_stories=1)
    del raw["story_defaults"]["shear_stiffness"]
    with pytest.raises(ValueError, match="requires shear_stiffness"):
        normalize_shear_flexure_config(raw)

    raw = _shear_flexure_raw(num_stories=1, shear_stiffness=-1.0)
    with pytest.raises(ValueError, match="shear_stiffness must be non-negative"):
        normalize_shear_flexure_config(raw)


def test_shear_flexure_golden_regression_signature() -> None:
    _assert_signature_matches(
        run_analysis(_shear_flexure_raw(num_stories=3), backend="direct"),
        "shear_flexure_3story.json",
    )


def test_cli_run_writes_shear_flexure_backend_outputs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    case_path = tmp_path / "shear_flexure.json"
    case_path.write_text(json.dumps(_shear_flexure_raw(num_stories=2)), encoding="utf-8")
    output = tmp_path / "run_output"

    exit_code = cli_main([
        "run",
        str(case_path),
        "--backend",
        "direct",
        "--output",
        str(output),
    ])

    assert exit_code == 0
    assert (output / "master_response.csv").exists()
    assert (output / "sensor_response.csv").exists()
    header = (output / "master_response.csv").read_text(encoding="utf-8").splitlines()[0]
    assert "theta" in header
    assert str(output) in capsys.readouterr().out


def _assert_euler_response_close(direct: AnalysisResult, opensees: AnalysisResult) -> None:
    assert opensees.metadata.backend == "opensees_euler"
    assert np.allclose(
        np.asarray(opensees.metadata.extras["opensees_frequency_hz"]),
        direct.modal.frequency,
        rtol=1.0e-8,
        atol=1.0e-8,
    )
    assert np.allclose(direct.relative.displacement, opensees.relative.displacement, atol=1.0e-14, rtol=1.0e-8)
    assert np.allclose(direct.relative.velocity, opensees.relative.velocity, atol=1.0e-12, rtol=1.0e-8)
    assert np.allclose(direct.relative.acceleration, opensees.relative.acceleration, atol=1.0e-10, rtol=1.0e-8)
    assert np.allclose(direct.absolute.acceleration, opensees.absolute.acceleration, atol=1.0e-10, rtol=1.0e-8)


def _assert_rayleigh_response_close(direct: AnalysisResult, opensees: AnalysisResult) -> None:
    assert opensees.metadata.backend == "opensees_rayleigh"
    assert np.allclose(
        np.asarray(opensees.metadata.extras["opensees_frequency_hz"]),
        direct.modal.frequency,
        rtol=1.0e-8,
        atol=1.0e-8,
    )
    assert np.allclose(direct.relative.displacement, opensees.relative.displacement, atol=1.0e-14, rtol=1.0e-8)
    assert np.allclose(direct.relative.velocity, opensees.relative.velocity, atol=1.0e-12, rtol=1.0e-8)
    assert np.allclose(direct.relative.acceleration, opensees.relative.acceleration, atol=1.0e-10, rtol=1.0e-8)
    assert np.allclose(direct.absolute.acceleration, opensees.absolute.acceleration, atol=1.0e-10, rtol=1.0e-8)


def _assert_timoshenko_response_close(direct: AnalysisResult, opensees: AnalysisResult) -> None:
    assert opensees.metadata.backend == "opensees_timoshenko"
    assert np.allclose(
        np.asarray(opensees.metadata.extras["opensees_frequency_hz"]),
        direct.modal.frequency,
        rtol=1.0e-8,
        atol=1.0e-8,
    )
    assert np.allclose(direct.relative.displacement, opensees.relative.displacement, atol=1.0e-14, rtol=1.0e-8)
    assert np.allclose(direct.relative.velocity, opensees.relative.velocity, atol=1.0e-12, rtol=1.0e-8)
    assert np.allclose(direct.relative.acceleration, opensees.relative.acceleration, atol=1.0e-10, rtol=1.0e-8)
    assert np.allclose(direct.absolute.acceleration, opensees.absolute.acceleration, atol=1.0e-10, rtol=1.0e-8)


def _assert_shear_flexure_response_close(direct: AnalysisResult, opensees: AnalysisResult) -> None:
    assert opensees.metadata.backend == "opensees_shear_flexure"
    assert np.allclose(
        np.asarray(opensees.metadata.extras["opensees_frequency_hz"]),
        direct.modal.frequency,
        rtol=1.0e-8,
        atol=1.0e-8,
    )
    assert np.allclose(direct.relative.displacement, opensees.relative.displacement, atol=1.0e-14, rtol=1.0e-8)
    assert np.allclose(direct.relative.velocity, opensees.relative.velocity, atol=1.0e-12, rtol=1.0e-8)
    assert np.allclose(direct.relative.acceleration, opensees.relative.acceleration, atol=1.0e-10, rtol=1.0e-8)
    assert np.allclose(direct.absolute.acceleration, opensees.absolute.acceleration, atol=1.0e-10, rtol=1.0e-8)


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


def test_geometry_normalization_accepts_heights_and_elevations() -> None:
    raw = _base_raw(num_stories=2)
    raw["geometry"] = {"story_heights": [4.5, 3.6]}
    config = normalize_config(raw)

    assert config.geometry.story_heights == (4.5, 3.6)
    assert config.geometry.elevations == (4.5, 8.1)

    raw["geometry"] = {"base_elevation": 1.0, "elevations": [4.0, 7.5]}
    config = normalize_config(raw)

    assert config.geometry.base_elevation == 1.0
    assert config.geometry.story_heights == (3.0, 3.5)
    assert config.geometry.elevations == (4.0, 7.5)


def test_geometry_normalization_rejects_invalid_height_contracts() -> None:
    raw = _base_raw(num_stories=2)
    raw["geometry"] = {"story_heights": [4.5]}
    with pytest.raises(ValueError, match="story_heights length"):
        normalize_config(raw)

    raw["geometry"] = {"elevations": [4.0, 4.0]}
    with pytest.raises(ValueError, match="strictly increasing"):
        normalize_config(raw)

    raw["geometry"] = {"story_heights": [4.0, 3.0], "elevations": [4.0, 8.0]}
    with pytest.raises(ValueError, match="inconsistent"):
        normalize_config(raw)


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


def test_zero_torsional_story_stiffness_is_rejected_early() -> None:
    raw = _base_raw(num_stories=1)
    raw["floor_defaults"]["elements"] = [
        {"id": "center", "x": 0.0, "y": 0.0, "kx": 2.0e8, "ky": 2.0e8},
    ]

    with pytest.raises(ValueError, match="Story 1 stiffness matrix.*positive definite"):
        run_analysis(raw, backend="direct")


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


def test_analysis_result_rejects_nonmonotonic_time() -> None:
    history = ResponseHistory(
        displacement=np.zeros((3, 1)),
        velocity=np.zeros((3, 1)),
        acceleration=np.zeros((3, 1)),
    )

    with pytest.raises(ValueError, match="strictly increasing"):
        AnalysisResult(
            time=np.array([0.0, 0.1, 0.1]),
            relative=history,
            mass_matrix=np.eye(1),
            stiffness_matrix=np.eye(1),
            damping_matrix=np.zeros((1, 1)),
            metadata=AnalysisMetadata(backend="test", response_definition="test"),
        )


def test_analysis_result_rejects_nonsymmetric_matrix() -> None:
    history = ResponseHistory(
        displacement=np.zeros((3, 2)),
        velocity=np.zeros((3, 2)),
        acceleration=np.zeros((3, 2)),
    )

    with pytest.raises(ValueError, match="stiffness_matrix must be symmetric"):
        AnalysisResult(
            time=np.array([0.0, 0.1, 0.2]),
            relative=history,
            mass_matrix=np.eye(2),
            stiffness_matrix=np.array([[1.0, 2.0], [0.0, 1.0]]),
            damping_matrix=np.zeros((2, 2)),
            metadata=AnalysisMetadata(backend="test", response_definition="test"),
        )


def test_rayleigh_rejects_repeated_reference_frequencies() -> None:
    raw = _base_raw(num_stories=1)
    raw["damping"] = {"type": "rayleigh", "zeta": 0.02, "modes": [1, 2]}

    with pytest.raises(ValueError, match="nearly identical natural frequencies"):
        run_analysis(raw, backend="direct")


def test_zero_rayleigh_damping_returns_zero_matrix_even_for_repeated_modes() -> None:
    raw = _base_raw(num_stories=1)
    raw["damping"] = {"type": "rayleigh", "zeta": 0.0, "modes": [1, 2]}

    result = run_analysis(raw, backend="direct")

    assert np.allclose(result.damping_matrix, 0.0)


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


def test_direct_shear_result_has_absolute_ground_and_sensor_semantics() -> None:
    config = normalize_shear_config(
        {
            "schema_version": "2.0",
            "model": {"type": "shear_building_1d", "num_stories": 2, "dof_per_floor": ["Ux"]},
            "floor_defaults": {"mass": 1.0e6, "stiffness": 8.0e8},
            "stories": [{"story": 1}, {"story": 2}],
            "sensors": [{"id": "roof_accel", "story": 2, "quantity": "accel"}],
            "damping": {"type": "rayleigh", "zeta": 0.02, "modes": [1, 2]},
            "ground_motion": {
                "dt": 0.01,
                "duration": 0.2,
                "synthetic": {"amplitude_x": 0.1, "amplitude_y": 0.0, "frequency_x": 1.0},
            },
        }
    )

    result = run_direct_shear_result(config)
    ground_x = result.ground.acceleration[:, 0]
    rows = result.sensors.rows

    assert result.absolute is not None
    assert result.ground is not None
    assert result.modal is not None
    assert np.allclose(
        result.absolute.acceleration,
        result.relative.acceleration + ground_x[:, None],
    )
    assert np.isclose(rows[-1]["value"], rows[-1]["abs_a"])
    assert np.isclose(rows[-1]["relative_value"], rows[-1]["a"])


def test_shear_golden_regression_signature() -> None:
    _assert_signature_matches(
        run_analysis(_golden_shear_raw(), backend="direct"),
        "shear_3story.json",
    )


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


def test_cli_validate_supports_separate_abs_and_relative_tolerances(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli_main([
        "validate",
        "shear1d/configs/shear_16story_external_gm.json",
        "--backend-a",
        "direct",
        "--backend-b",
        "direct",
        "--abs-tol",
        "0.0",
        "--rel-tol",
        "0.0",
    ])

    assert exit_code == 0
    assert "relative_l2" in capsys.readouterr().out


def test_symmetric_relative_l2_preserves_small_response_scale() -> None:
    a = np.array([1.0e-6, 0.0])
    b = np.array([2.0e-6, 0.0])

    assert np.isclose(symmetric_relative_l2(a, b), 2.0 / 3.0)

    metrics = compare_master_arrays(
        {
            "displacement": a,
            "velocity": np.zeros(2),
            "acceleration": np.zeros(2),
        },
        {
            "displacement": b,
            "velocity": np.zeros(2),
            "acceleration": np.zeros(2),
        },
    )

    assert np.isclose(metrics["displacement_relative_l2"], 2.0 / 3.0)
    assert metrics["velocity_relative_l2"] == 0.0


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


def test_thin_scripts_reexport_library_entry_points() -> None:
    assert legacy_metadata.build_qrest_metadata is build_qrest_metadata
    assert legacy_algorithm_configs.write_algorithm_configs is write_algorithm_configs
    assert legacy_map_sensors.map_sensors is map_sensors


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


def test_qrest_metadata_uses_geometry_elevations() -> None:
    raw = _base_raw(num_stories=2)
    raw["geometry"] = {"story_heights": [4.5, 3.6]}
    raw["sensors"] = [
        {"id": "first", "story": 1, "x": 0.0, "y": 0.0, "direction": "X"},
        {"id": "second", "story": 2, "x": 0.0, "y": 0.0, "direction": "Y"},
    ]

    metadata = build_qrest_metadata(raw, npts=11)

    assert metadata["BuildingInfo"]["Elevation"] == [4.5, 8.1]
    assert metadata["InstrumentInfo"]["Channels"][0]["LocationXYZ"] == [0.0, 0.0, 4.5]
    assert metadata["InstrumentInfo"]["Channels"][1]["LocationXYZ"] == [0.0, 0.0, 8.1]


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
    result = run_analysis(raw, backend="direct")

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
    assert channels[0]["LocationXYZ"] == [0.0, -3.0, 3.0]
    assert channels[-1]["LocationXYZ"] == [5.0, 0.0, 48.0]
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
    assert channels[0]["LocationXYZ"] == [0.0, -3.0, 3.0]
    assert channels[1]["LocationXYZ"] == [0.0, 3.0, 3.0]
    assert channels[10]["LocationXYZ"] == [0.0, 0.0, 3.0]
    assert channels[-1]["LocationXYZ"] == [0.0, 0.0, 48.0]
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


@pytest.mark.opensees
def test_opensees_matches_direct_for_simple_damped_no_torsion_case(tmp_path: Path) -> None:
    _require_opensees_tests()

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
    direct = run_analysis(raw, backend="direct")
    opensees = run_analysis(raw, backend="opensees")

    _assert_response_close(direct, opensees, displacement_atol=1.0e-10, velocity_atol=1.0e-9, acceleration_atol=1.0e-8)


@pytest.mark.opensees
def test_opensees_matches_direct_for_multistory_symmetric_case() -> None:
    _require_opensees_tests()
    raw = _base_raw(num_stories=3)
    raw["sensors"] = []
    raw["ground_motion"] = {
        "dt": 0.01,
        "duration": 0.2,
        "synthetic": {"amplitude_x": 0.08, "amplitude_y": 0.03, "frequency_x": 0.9, "frequency_y": 1.1},
    }

    _assert_response_close(run_analysis(raw, backend="direct"), run_analysis(raw, backend="opensees"))


@pytest.mark.opensees
def test_opensees_matches_direct_for_eccentric_sensor_case() -> None:
    _require_opensees_tests()
    raw = _base_raw(num_stories=2)
    raw["floor_defaults"]["mass_center"] = [0.2, 0.3]
    raw["sensors"] = [
        {"id": "roof_x_ypos", "story": 2, "x": 5.0, "y": 3.0, "direction": "X"},
        {"id": "roof_y_xpos", "story": 2, "x": 5.0, "y": 0.0, "direction": "Y"},
        {"id": "roof_rz", "story": 2, "x": 0.0, "y": 0.0, "direction": "RZ"},
    ]
    raw["ground_motion"] = {
        "dt": 0.01,
        "duration": 0.2,
        "synthetic": {"amplitude_x": 0.1, "amplitude_y": 0.05, "frequency_x": 1.0, "frequency_y": 0.7},
    }
    direct = run_analysis(raw, backend="direct")
    opensees = run_analysis(raw, backend="opensees")

    _assert_response_close(direct, opensees)
    assert np.allclose(
        [row["value"] for row in direct.sensors.rows],
        [row["value"] for row in opensees.sensors.rows],
        atol=1.0e-6,
        rtol=1.0e-7,
    )


@pytest.mark.opensees
def test_opensees_matches_direct_for_variable_story_stiffness_case() -> None:
    _require_opensees_tests()
    raw = _base_raw(num_stories=3)
    raw["stories"] = [
        {"story": 1, "elements": _scaled_corner_elements(1.0)},
        {"story": 2, "elements": _scaled_corner_elements(0.9)},
        {"story": 3, "elements": _scaled_corner_elements(0.75)},
    ]
    raw["sensors"] = []

    _assert_response_close(run_analysis(raw, backend="direct"), run_analysis(raw, backend="opensees"))


@pytest.mark.opensees
def test_opensees_shear_matches_direct_for_three_story_case() -> None:
    _require_opensees_tests()
    raw = _golden_shear_raw()

    _assert_response_close(run_analysis(raw, backend="direct"), run_analysis(raw, backend="opensees"))


@pytest.mark.opensees
def test_opensees_euler_matches_direct_for_one_story_case() -> None:
    _require_opensees_tests()
    raw = _euler_raw(num_stories=1)

    _assert_euler_response_close(run_analysis(raw, backend="direct"), run_analysis(raw, backend="opensees"))


@pytest.mark.opensees
def test_opensees_euler_matches_direct_for_three_story_case() -> None:
    _require_opensees_tests()
    raw = _euler_raw(num_stories=3)

    _assert_euler_response_close(run_analysis(raw, backend="direct"), run_analysis(raw, backend="opensees"))


@pytest.mark.opensees
def test_opensees_euler_matches_direct_for_variable_section_case() -> None:
    _require_opensees_tests()
    raw = _euler_raw(num_stories=3)
    raw["geometry"] = {"story_heights": [4.5, 3.6, 3.2]}
    raw["sections"] = [
        {"story": 1, "I": 110.0},
        {"story": 2, "I": 90.0},
        {"story": 3, "I": 70.0, "density": 2400.0},
    ]

    _assert_euler_response_close(run_analysis(raw, backend="direct"), run_analysis(raw, backend="opensees"))


@pytest.mark.opensees
def test_opensees_rayleigh_matches_direct_for_one_story_case() -> None:
    _require_opensees_tests()
    raw = _rayleigh_raw(num_stories=1)

    _assert_rayleigh_response_close(run_analysis(raw, backend="direct"), run_analysis(raw, backend="opensees"))


@pytest.mark.opensees
def test_opensees_rayleigh_matches_direct_for_three_story_case() -> None:
    _require_opensees_tests()
    raw = _rayleigh_raw(num_stories=3)

    _assert_rayleigh_response_close(run_analysis(raw, backend="direct"), run_analysis(raw, backend="opensees"))


@pytest.mark.opensees
def test_opensees_rayleigh_matches_direct_for_variable_inertia_case() -> None:
    _require_opensees_tests()
    raw = _rayleigh_raw(num_stories=3)
    raw["geometry"] = {"story_heights": [4.5, 3.6, 3.2]}
    raw["sections"] = [
        {"story": 1, "I": 110.0, "rotational_inertia": 3.0e5},
        {"story": 2, "I": 90.0, "rotational_inertia": 2.0e5},
        {"story": 3, "I": 70.0, "density": 2400.0, "rotational_inertia": 1.0e5},
    ]

    _assert_rayleigh_response_close(run_analysis(raw, backend="direct"), run_analysis(raw, backend="opensees"))


@pytest.mark.opensees
def test_opensees_timoshenko_matches_direct_for_one_story_case() -> None:
    _require_opensees_tests()
    raw = _timoshenko_raw(num_stories=1)

    _assert_timoshenko_response_close(run_analysis(raw, backend="direct"), run_analysis(raw, backend="opensees"))


@pytest.mark.opensees
def test_opensees_timoshenko_matches_direct_for_three_story_case() -> None:
    _require_opensees_tests()
    raw = _timoshenko_raw(num_stories=3)

    _assert_timoshenko_response_close(run_analysis(raw, backend="direct"), run_analysis(raw, backend="opensees"))


@pytest.mark.opensees
def test_opensees_timoshenko_matches_direct_for_variable_shear_case() -> None:
    _require_opensees_tests()
    raw = _timoshenko_raw(num_stories=3)
    raw["geometry"] = {"story_heights": [4.5, 3.6, 3.2]}
    raw["sections"] = [
        {"story": 1, "I": 110.0, "G": 1.1e10, "shear_area": 18.0},
        {"story": 2, "I": 90.0, "G": 1.25e10, "shear_area": 16.0},
        {"story": 3, "I": 70.0, "density": 2400.0, "G": 1.4e10, "shear_area": 14.0},
    ]

    _assert_timoshenko_response_close(run_analysis(raw, backend="direct"), run_analysis(raw, backend="opensees"))


@pytest.mark.opensees
def test_opensees_shear_flexure_matches_direct_for_one_story_case() -> None:
    _require_opensees_tests()
    raw = _shear_flexure_raw(num_stories=1)

    _assert_shear_flexure_response_close(run_analysis(raw, backend="direct"), run_analysis(raw, backend="opensees"))


@pytest.mark.opensees
def test_opensees_shear_flexure_matches_direct_for_three_story_case() -> None:
    _require_opensees_tests()
    raw = _shear_flexure_raw(num_stories=3)

    _assert_shear_flexure_response_close(run_analysis(raw, backend="direct"), run_analysis(raw, backend="opensees"))


@pytest.mark.opensees
def test_opensees_shear_flexure_matches_direct_for_variable_branch_case() -> None:
    _require_opensees_tests()
    raw = _shear_flexure_raw(num_stories=3)
    raw["geometry"] = {"story_heights": [4.5, 3.6, 3.2]}
    raw["stories"] = [
        {"story": 1, "flexural_section": {"I": 110.0}, "shear_stiffness": 7.0e8},
        {"story": 2, "flexural_section": {"I": 90.0}, "shear_stiffness": 8.0e8},
        {"story": 3, "flexural_section": {"I": 70.0, "density": 2400.0}, "shear_stiffness": 9.0e8},
    ]

    _assert_shear_flexure_response_close(run_analysis(raw, backend="direct"), run_analysis(raw, backend="opensees"))
