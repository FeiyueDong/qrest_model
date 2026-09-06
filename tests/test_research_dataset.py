from __future__ import annotations

import csv
import json
import warnings
from pathlib import Path

import numpy as np
import pytest

from qrest_model.cli import main as cli_main
from qrest_model.backends import run_analysis
from qrest_model.datasets.cases import RESEARCH_CONFIG_ROOT, load_dataset_case, research_cases, schema_model_type
from qrest_model.datasets.observations import apply_observation_config
from qrest_model.datasets.research import generate_research_cases, generate_research_dataset
from qrest_model.datasets.validation import validate_research_dataset, validate_research_dataset_collection
from qrest_model.exporters.qrest_metadata import build_qrest_metadata_from_research_dataset
from qrest_model.exporters.qrest_dataset import export_dataset
from qrest_model.noise import apply_observation_noise
from qrest_model.observations.series import extract_observation_series
from qrest_model.schema import (
    EULER_BEAM_2D,
    RAYLEIGH_BEAM_2D,
    RIGID_FLOOR_SHEAR_3D,
    SHEAR_FLEXURE_BUILDING_2D,
    SHEAR_BUILDING_1D,
    TIMOSHENKO_BEAM_2D,
)


MODEL_ROOT = Path(__file__).resolve().parents[1]
EULER_CASE = MODEL_ROOT / "beam2d" / "configs" / "euler_3story.json"


def test_research_dataset_separates_truth_physical_and_virtual_observations(tmp_path: Path) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        output = generate_research_dataset(
            EULER_CASE,
            tmp_path / "euler_research",
            name="euler_research",
        )

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    observation = json.loads((output / "metadata" / "observation.json").read_text(encoding="utf-8"))
    provenance = json.loads((output / "metadata" / "provenance.json").read_text(encoding="utf-8"))
    noise = json.loads((output / "metadata" / "noise.json").read_text(encoding="utf-8"))

    assert manifest["dataset_type"] == "research"
    assert manifest["model_type"] == "euler_beam_2d"
    assert manifest["deterministic"] is True
    assert manifest["config_hash_sha256"] == provenance["config_hash_sha256"]
    assert manifest["model_config_hash_sha256"] == provenance["model_config_hash_sha256"]
    assert manifest["dataset_config_hash_sha256"] == provenance["dataset_config_hash_sha256"]
    assert manifest["derived"] == {"directory": "derived", "structural": "structural.npz"}
    assert manifest["metadata"]["derived"] == "metadata/derived.json"
    assert manifest["metadata"]["noise"] == "metadata/noise.json"
    assert manifest["noise"]["configured"] is False
    assert noise["enabled"] is False
    assert manifest["content_summary"] == {
        "time_steps": 11,
        "dof_count": 6,
        "physical_channel_count": 1,
        "virtual_channel_count": 1,
        "observation_quantities": ["acceleration", "displacement"],
        "derived_quantity_ids": [
            "inter_story_displacement_u",
            "inter_story_drift_ratio_u",
            "story_rotation_difference",
        ],
    }
    assert observation["physical_channel_count"] == 1
    assert observation["virtual_channel_count"] == 1
    assert observation["files"]["physical"] == {"acceleration": "physical/acceleration.csv"}
    assert observation["files"]["virtual"] == {"displacement": "virtual/displacement.csv"}
    assert [channel["id"] for channel in observation["channels"]] == ["roof_u", "roof_theta"]
    assert [channel["kind"] for channel in observation["channels"]] == ["physical", "virtual"]
    assert [channel["unit"] for channel in observation["channels"]] == ["m/s^2", "rad"]
    assert observation["channels"][0]["operator"] == {
        "form": "linear_combination",
        "terms": [{"frame": "absolute", "quantity": "acceleration", "story": 3, "dof": "U", "coefficient": 1.0}],
    }
    assert observation["channels"][1]["operator"] == {
        "form": "linear_combination",
        "terms": [{"frame": "relative", "quantity": "displacement", "story": 3, "dof": "Theta", "coefficient": 1.0}],
    }

    with np.load(output / "truth" / "response.npz") as response:
        assert response["relative_displacement"].shape == (11, 3, 2)
        assert response["absolute_acceleration"].shape == (11, 3, 2)
    with np.load(output / "truth" / "matrices.npz") as matrices:
        assert matrices["mass_matrix"].shape == (6, 6)
        assert matrices["dof_labels"].tolist() == [
            "story_01_u",
            "story_01_theta",
            "story_02_u",
            "story_02_theta",
            "story_03_u",
            "story_03_theta",
        ]
    derived = json.loads((output / "metadata" / "derived.json").read_text(encoding="utf-8"))
    assert {quantity["id"] for quantity in derived["quantities"]} == {
        "inter_story_displacement_u",
        "inter_story_drift_ratio_u",
        "story_rotation_difference",
    }
    assert {quantity["unit"] for quantity in derived["quantities"]} == {"m", "1", "rad"}
    with np.load(output / "derived" / "structural.npz") as values:
        assert values["inter_story_displacement_u"].shape == (11, 3)
        assert values["story_rotation_difference"].shape == (11, 3)
    structural = json.loads((output / "truth" / "structural_properties.json").read_text(encoding="utf-8"))
    assert structural["modal_metadata"]["mode_shape_normalization"] == "mass_normalized"
    assert structural["modal_metadata"]["mode_shape_sign_convention"] == "largest_abs_component_positive"
    assert structural["dof_units"]["story_03_theta"] == "rad"
    assert structural["dof_units"]["story_03_u"] == "m"

    assert _csv_header(output / "observations" / "physical" / "acceleration.csv") == ["time", "roof_u"]
    assert _csv_header(output / "observations" / "virtual" / "displacement.csv") == ["time", "roof_theta"]
    assert validate_research_dataset(output) == {
        "name": "euler_research",
        "model_type": "euler_beam_2d",
        "time_steps": 11,
        "physical_channel_count": 1,
        "virtual_channel_count": 1,
    }


def test_research_dataset_generation_is_reproducible(tmp_path: Path) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        first = generate_research_dataset(EULER_CASE, tmp_path / "first", name="repro")
        second = generate_research_dataset(EULER_CASE, tmp_path / "second", name="repro")

    assert (first / "manifest.json").read_text(encoding="utf-8") == (
        second / "manifest.json"
    ).read_text(encoding="utf-8")
    assert (first / "metadata" / "observation.json").read_text(encoding="utf-8") == (
        second / "metadata" / "observation.json"
    ).read_text(encoding="utf-8")
    with np.load(first / "truth" / "response.npz") as a, np.load(second / "truth" / "response.npz") as b:
        assert np.allclose(a["relative_acceleration"], b["relative_acceleration"])


def test_research_dataset_uses_top_level_observations_as_runtime_source(tmp_path: Path) -> None:
    case = json.loads((RESEARCH_CONFIG_ROOT / "oma_shear_3story.json").read_text(encoding="utf-8"))
    case["model_config"]["sensors"] = [{"id": "legacy_01f_x", "story": 1, "quantity": "accel"}]
    case["observations"] = {
        "physical": {
            "stories": [3],
            "directions": ["X"],
            "quantity": "acceleration",
        }
    }

    output = generate_research_dataset(case, tmp_path / "single_source")
    observation = json.loads((output / "metadata" / "observation.json").read_text(encoding="utf-8"))
    runtime_config = json.loads((output / "config.json").read_text(encoding="utf-8"))

    assert [channel["id"] for channel in observation["channels"]] == ["03f_x"]
    assert [sensor["id"] for sensor in runtime_config["sensors"]] == ["03f_x"]
    assert _csv_header(output / "observations" / "physical" / "acceleration.csv") == ["time", "03f_x"]
    with np.load(output / "truth" / "response.npz") as response:
        truth = response["relative_acceleration"].copy()

    case["observations"] = {
        "physical": {
            "stories": [1],
            "directions": ["X"],
            "quantity": "acceleration",
        }
    }
    changed = generate_research_dataset(case, tmp_path / "single_source_changed")
    changed_observation = json.loads((changed / "metadata" / "observation.json").read_text(encoding="utf-8"))

    assert [channel["id"] for channel in changed_observation["channels"]] == ["01f_x"]
    with np.load(changed / "truth" / "response.npz") as response:
        assert np.allclose(response["relative_acceleration"], truth)


def test_research_dataset_gaussian_noise_keeps_truth_and_clean_reference(tmp_path: Path) -> None:
    clean_case = json.loads((RESEARCH_CONFIG_ROOT / "mbi_euler_3story_sparse.json").read_text(encoding="utf-8"))
    noisy_case = json.loads(json.dumps(clean_case))
    noisy_case["noise"] = {
        "enabled": True,
        "seed": 20260906,
        "model": {"type": "gaussian_white", "target": "physical"},
        "level": {"mode": "std_ratio", "value": 0.05},
    }

    clean = generate_research_dataset(clean_case, tmp_path / "clean")
    noisy = generate_research_dataset(noisy_case, tmp_path / "noisy")

    assert _csv_matrix(noisy / "observations" / "physical_clean" / "acceleration.csv").shape == (
        11,
        3,
    )
    assert np.allclose(
        _csv_matrix(clean / "observations" / "physical" / "acceleration.csv"),
        _csv_matrix(noisy / "observations" / "physical_clean" / "acceleration.csv"),
    )
    assert not np.allclose(
        _csv_matrix(noisy / "observations" / "physical" / "acceleration.csv"),
        _csv_matrix(noisy / "observations" / "physical_clean" / "acceleration.csv"),
    )
    assert np.allclose(
        _csv_matrix(clean / "observations" / "virtual" / "displacement.csv"),
        _csv_matrix(noisy / "observations" / "virtual" / "displacement.csv"),
    )
    with np.load(clean / "truth" / "response.npz") as a, np.load(noisy / "truth" / "response.npz") as b:
        assert np.allclose(a["relative_displacement"], b["relative_displacement"])
        assert np.allclose(a["relative_acceleration"], b["relative_acceleration"])

    manifest = json.loads((noisy / "manifest.json").read_text(encoding="utf-8"))
    clean_manifest = json.loads((clean / "manifest.json").read_text(encoding="utf-8"))
    noise = json.loads((noisy / "metadata" / "noise.json").read_text(encoding="utf-8"))
    observation = json.loads((noisy / "metadata" / "observation.json").read_text(encoding="utf-8"))
    assert manifest["noise"]["configured"] is True
    assert manifest["model_config_hash_sha256"] == clean_manifest["model_config_hash_sha256"]
    assert manifest["dataset_config_hash_sha256"] != clean_manifest["dataset_config_hash_sha256"]
    assert observation["files"]["physical_clean"] == {"acceleration": "physical_clean/acceleration.csv"}
    assert noise["enabled"] is True
    assert noise["type"] == "gaussian_white"
    assert noise["seed"] == 20260906
    assert len(noise["channels"]) == 2
    assert all(channel["target_noise_std"] > 0.0 for channel in noise["channels"])
    assert validate_research_dataset(noisy)["physical_channel_count"] == 2


def test_research_dataset_noise_requires_explicit_seed(tmp_path: Path) -> None:
    case = json.loads((RESEARCH_CONFIG_ROOT / "mbi_shear_3story_sparse.json").read_text(encoding="utf-8"))
    case["noise"] = {
        "enabled": True,
        "model": {"type": "gaussian_white", "target": "physical"},
        "level": {"mode": "std_ratio", "value": 0.01},
    }

    with pytest.raises(ValueError, match="requires an explicit seed"):
        generate_research_dataset(case, tmp_path / "missing_seed")


def test_rigid_floor_noise_uses_scalar_physical_channel_series(tmp_path: Path) -> None:
    case = json.loads((RESEARCH_CONFIG_ROOT / "mbi_rigid_3story_sparse.json").read_text(encoding="utf-8"))
    case["noise"] = {
        "enabled": True,
        "seed": 20260907,
        "model": {"type": "gaussian_white", "target": "physical"},
        "level": {"mode": "std_ratio", "value": 0.05},
    }

    output = generate_research_dataset(case, tmp_path / "rigid_noisy")

    clean = _csv_matrix(output / "observations" / "physical_clean" / "acceleration.csv")[:, 1:]
    measured = _csv_matrix(output / "observations" / "physical" / "acceleration.csv")[:, 1:]
    noise = json.loads((output / "metadata" / "noise.json").read_text(encoding="utf-8"))
    assert len(noise["channels"]) == clean.shape[1]
    for index, channel in enumerate(noise["channels"]):
        signal_std = float(np.std(clean[:, index]))
        assert channel["id"] in {"01f_x", "03f_x", "03f_y"}
        assert channel["signal_std"] == pytest.approx(signal_std)
        assert channel["target_noise_std"] == pytest.approx(0.05 * signal_std)
        assert np.std(measured[:, index] - clean[:, index]) == pytest.approx(channel["realized_noise_std"])


def test_noisy_observation_rows_are_refreshed_from_current_history() -> None:
    case = load_dataset_case(RESEARCH_CONFIG_ROOT / "mbi_rigid_3story_sparse.json")
    config = apply_observation_config(case.config, case.observation_config)
    result = run_analysis(config, backend="direct")
    noisy, _metadata = apply_observation_noise(
        result.observations,
        {
            "enabled": True,
            "seed": 20260907,
            "model": {"type": "gaussian_white", "target": "physical"},
            "level": {"mode": "std_ratio", "value": 0.05},
        },
    )

    step_count = result.time.size
    first_channel_series = extract_observation_series(noisy, 0, absolute=True)
    first_relative_series = extract_observation_series(noisy, 0, absolute=False)
    first_channel_rows = noisy.rows[:step_count]

    assert [row["value"] for row in first_channel_rows] == pytest.approx(first_channel_series)
    assert [row["relative_value"] for row in first_channel_rows] == pytest.approx(first_relative_series)
    assert [row["abs_ax"] for row in first_channel_rows] == pytest.approx(first_channel_series)
    assert not np.allclose(
        [row["value"] for row in first_channel_rows],
        [row["value"] for row in result.observations.rows[:step_count]],
    )


def test_research_dataset_noise_seed_reproducibility(tmp_path: Path) -> None:
    case = json.loads((RESEARCH_CONFIG_ROOT / "mbi_shear_3story_sparse.json").read_text(encoding="utf-8"))
    case["noise"] = {
        "enabled": True,
        "seed": 100,
        "model": {"type": "gaussian_white", "target": "physical"},
        "level": {"mode": "std_ratio", "value": 0.10},
    }
    same_seed = json.loads(json.dumps(case))
    other_seed = json.loads(json.dumps(case))
    other_seed["noise"]["seed"] = 101

    first = generate_research_dataset(case, tmp_path / "first")
    second = generate_research_dataset(same_seed, tmp_path / "second")
    third = generate_research_dataset(other_seed, tmp_path / "third")

    assert np.allclose(
        _csv_matrix(first / "observations" / "physical" / "acceleration.csv"),
        _csv_matrix(second / "observations" / "physical" / "acceleration.csv"),
    )
    assert not np.allclose(
        _csv_matrix(first / "observations" / "physical" / "acceleration.csv"),
        _csv_matrix(third / "observations" / "physical" / "acceleration.csv"),
    )
    assert np.allclose(
        _csv_matrix(first / "observations" / "physical_clean" / "acceleration.csv"),
        _csv_matrix(third / "observations" / "physical_clean" / "acceleration.csv"),
    )


def test_research_dataset_zero_noise_level_matches_clean_observation(tmp_path: Path) -> None:
    case = json.loads((RESEARCH_CONFIG_ROOT / "mbi_shear_3story_sparse.json").read_text(encoding="utf-8"))
    case["noise"] = {
        "enabled": True,
        "seed": 100,
        "model": {"type": "gaussian_white", "target": "physical"},
        "level": {"mode": "std_ratio", "value": 0.0},
    }

    output = generate_research_dataset(case, tmp_path / "zero_noise")

    assert np.allclose(
        _csv_matrix(output / "observations" / "physical" / "acceleration.csv"),
        _csv_matrix(output / "observations" / "physical_clean" / "acceleration.csv"),
    )
    noise = json.loads((output / "metadata" / "noise.json").read_text(encoding="utf-8"))
    assert all(channel["target_noise_std"] == 0.0 for channel in noise["channels"])


def test_qrest_export_uses_noisy_research_physical_observations(tmp_path: Path) -> None:
    case = json.loads((RESEARCH_CONFIG_ROOT / "mbi_shear_3story_sparse.json").read_text(encoding="utf-8"))
    case["noise"] = {
        "enabled": True,
        "seed": 20260906,
        "model": {"type": "gaussian_white", "target": "physical"},
        "level": {"mode": "std_ratio", "value": 0.05},
    }
    dataset = generate_research_dataset(case, tmp_path / "research_noisy")

    exported = export_dataset(dataset, tmp_path / "qrest_noisy", config_source=None)

    measured = _csv_matrix(dataset / "observations" / "physical" / "acceleration.csv")[:, 1:]
    clean = _csv_matrix(dataset / "observations" / "physical_clean" / "acceleration.csv")[:, 1:]
    exported_values = _text_matrix(exported / "qrest_noisy_data.txt")
    metadata = json.loads((exported / "qrest_noisy_metadata.json").read_text(encoding="utf-8"))
    oma_config = json.loads((exported / "config/oma/FrequencyDomainDecomposition.json").read_text(encoding="utf-8"))
    assert np.allclose(exported_values, measured)
    assert not np.allclose(exported_values, clean)
    assert metadata["InstrumentInfo"]["ChannelNum"] == measured.shape[1]
    assert [channel["ChannelID"] for channel in metadata["InstrumentInfo"]["Channels"]] == ["01f_x", "03f_x"]
    assert oma_config["init_frequencies"] == []


def test_qrest_metadata_can_be_built_from_research_dataset(tmp_path: Path) -> None:
    dataset = generate_research_dataset(
        RESEARCH_CONFIG_ROOT / "oma_shear_12story_stochastic.json",
        tmp_path / "oma_stochastic",
    )

    metadata = build_qrest_metadata_from_research_dataset(dataset)

    assert metadata["BuildingInfo"]["ProjectName"] == "qREST_Model_oma_shear_12story_stochastic"
    assert metadata["DataInfo"]["NPTS"] == 501
    assert metadata["DataInfo"]["DT"] == 0.01
    assert metadata["InstrumentInfo"]["ChannelNum"] == 12
    assert [channel["ChannelID"] for channel in metadata["InstrumentInfo"]["Channels"][:2]] == ["01f_x", "02f_x"]


def test_cli_generate_research_dataset_runs_and_validates(tmp_path: Path, capsys) -> None:
    output = tmp_path / "research_cli"

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        exit_code = cli_main([
            "generate-research",
            str(EULER_CASE),
            "--output",
            str(output),
            "--name",
            "cli_research",
            "--validate",
        ])

    assert exit_code == 0
    assert (output / "manifest.json").exists()
    assert "physical_channel_count: 1" in capsys.readouterr().out


def test_research_dataset_validation_rejects_missing_observation_operator(tmp_path: Path) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        output = generate_research_dataset(EULER_CASE, tmp_path / "euler_research")

    observation_path = output / "metadata" / "observation.json"
    observation = json.loads(observation_path.read_text(encoding="utf-8"))
    del observation["channels"][0]["operator"]
    observation_path.write_text(json.dumps(observation, indent=2), encoding="utf-8")

    with pytest.raises(ValueError, match="missing observation operator"):
        validate_research_dataset(output)


def test_research_dataset_derived_inter_story_drift_matches_truth(tmp_path: Path) -> None:
    case_path = RESEARCH_CONFIG_ROOT / "oma_shear_3story.json"
    output = generate_research_dataset(case_path, tmp_path / "shear_research")

    with np.load(output / "truth" / "response.npz") as response, np.load(output / "derived" / "structural.npz") as derived:
        displacement = response["relative_displacement"]
        lower = np.column_stack([np.zeros(displacement.shape[0]), displacement[:, :-1]])
        expected_inter_story = displacement - lower
        assert np.allclose(derived["inter_story_displacement_x"], expected_inter_story)
        assert np.allclose(derived["inter_story_drift_ratio_x"], expected_inter_story / 3.0)


def test_research_dataset_validation_rejects_broken_derived_metadata(tmp_path: Path) -> None:
    output = generate_research_dataset(RESEARCH_CONFIG_ROOT / "oma_shear_3story.json", tmp_path / "shear_research")
    derived_path = output / "metadata" / "derived.json"
    derived = json.loads(derived_path.read_text(encoding="utf-8"))
    derived["quantities"][0]["unit"] = ""
    derived_path.write_text(json.dumps(derived, indent=2), encoding="utf-8")

    with pytest.raises(ValueError, match="missing unit"):
        validate_research_dataset(output)


def test_research_case_definitions_cover_supported_schema_families() -> None:
    cases = {case.name: case for case in research_cases()}

    assert set(cases) == {
        "oma_shear_3story",
        "oma_shear_12story_research",
        "oma_shear_12story_stochastic",
        "oma_euler_3story",
        "oma_timoshenko_3story",
        "oma_timoshenko_12story_stochastic",
        "mbi_shear_3story_sparse",
        "mbi_euler_3story_sparse",
        "mbi_rigid_3story_sparse",
        "mbi_rayleigh_3story_sparse",
        "mbi_timoshenko_3story_sparse",
        "mbi_timoshenko_16story_research",
        "mbi_timoshenko_16story_sparse_research",
        "mbi_shear_flexure_3story_sparse",
        "rr_shear_12story_sparse_research",
    }
    assert {case.model_type for case in cases.values()} == {
        SHEAR_BUILDING_1D,
        EULER_BEAM_2D,
        RIGID_FLOOR_SHEAR_3D,
        RAYLEIGH_BEAM_2D,
        TIMOSHENKO_BEAM_2D,
        SHEAR_FLEXURE_BUILDING_2D,
    }
    assert {path.stem for path in RESEARCH_CONFIG_ROOT.glob("*.json")} == set(cases)
    assert schema_model_type("shear1d") == SHEAR_BUILDING_1D
    assert schema_model_type("story3d") == RIGID_FLOOR_SHEAR_3D
    assert schema_model_type(EULER_BEAM_2D) == EULER_BEAM_2D


def test_research_case_definitions_cover_oma_and_mbi_acceptance_families() -> None:
    cases = research_cases()
    oma_families = {case.research.get("family") for case in cases if case.research.get("task") == "oma"}
    mbi_families = {
        case.research.get("family")
        for case in cases
        if case.research.get("task") in {"mode_completion", "model_based_identification"}
    }

    assert oma_families >= {"shear", "euler", "timoshenko"}
    assert mbi_families >= {"shear", "euler", "timoshenko", "shear_flexure"}
    small = {case.name for case in cases if case.research.get("scale") == "small_regression"}
    research_scale = {case.name for case in cases if case.research.get("scale") == "research_scale"}
    assert len(small) == 9
    assert research_scale == {
        "oma_shear_12story_research",
        "oma_shear_12story_stochastic",
        "oma_timoshenko_12story_stochastic",
        "mbi_timoshenko_16story_research",
        "mbi_timoshenko_16story_sparse_research",
        "rr_shear_12story_sparse_research",
    }
    stochastic = {case.name for case in cases if case.research.get("excitation") == "stochastic"}
    assert stochastic == {"oma_shear_12story_stochastic", "oma_timoshenko_12story_stochastic"}
    response_reconstruction = {
        case.name
        for case in cases
        if case.research.get("task") == "response_reconstruction"
    }
    assert response_reconstruction == {"rr_shear_12story_sparse_research"}


def test_research_scale_cases_have_standard_metadata() -> None:
    required_keys = {"task", "family", "excitation", "sensor_density", "noise_level", "scale"}
    for case in research_cases():
        if case.research.get("scale") != "research_scale":
            continue
        assert required_keys <= set(case.research), case.name


def test_generate_research_cases_runs_all_configured_cases(tmp_path: Path) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        generated = generate_research_cases(tmp_path / "research")

    assert {path.name for path in generated} == {
        "oma_shear_3story",
        "oma_shear_12story_research",
        "oma_shear_12story_stochastic",
        "oma_euler_3story",
        "oma_timoshenko_3story",
        "oma_timoshenko_12story_stochastic",
        "mbi_shear_3story_sparse",
        "mbi_euler_3story_sparse",
        "mbi_rigid_3story_sparse",
        "mbi_rayleigh_3story_sparse",
        "mbi_timoshenko_3story_sparse",
        "mbi_timoshenko_16story_research",
        "mbi_timoshenko_16story_sparse_research",
        "mbi_shear_flexure_3story_sparse",
        "rr_shear_12story_sparse_research",
    }
    assert (tmp_path / "research" / "manifest.json").exists()
    for path in generated:
        summary = validate_research_dataset(path)
        assert summary["name"] == path.name
        assert summary["physical_channel_count"] > 0
    collection = validate_research_dataset_collection(tmp_path / "research")
    assert collection["dataset_count"] == 15


def test_research_benchmarks_include_oma_truth_and_mbi_observation_layout(tmp_path: Path) -> None:
    selected = [
        "oma_shear_3story",
        "oma_euler_3story",
        "oma_timoshenko_3story",
        "mbi_shear_3story_sparse",
        "mbi_euler_3story_sparse",
        "mbi_timoshenko_3story_sparse",
        "mbi_shear_flexure_3story_sparse",
    ]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        generated = generate_research_cases(tmp_path / "research", selected)

    for path in generated:
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        observation = json.loads((path / "metadata" / "observation.json").read_text(encoding="utf-8"))
        with np.load(path / "truth" / "modal.npz") as modal:
            assert modal["frequency_hz"].size > 0
            assert modal["mode_shapes"].ndim == 2
        if manifest["research"]["task"] == "oma":
            assert manifest["truth"]["modal"] == "modal.npz"
        else:
            measured = [channel for channel in observation["channels"] if channel["kind"] == "physical"]
            assert measured
            assert all("operator" in channel for channel in measured)


def test_research_scale_benchmarks_are_representative(tmp_path: Path) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        generated = {
            path.name: path
            for path in generate_research_cases(
                tmp_path / "research",
                [
                    "oma_shear_12story_research",
                    "mbi_timoshenko_16story_research",
                    "mbi_timoshenko_16story_sparse_research",
                    "rr_shear_12story_sparse_research",
                ],
            )
        }

    oma = generated["oma_shear_12story_research"]
    mbi = generated["mbi_timoshenko_16story_research"]
    mbi_sparse = generated["mbi_timoshenko_16story_sparse_research"]
    rr = generated["rr_shear_12story_sparse_research"]
    oma_manifest = json.loads((oma / "manifest.json").read_text(encoding="utf-8"))
    mbi_manifest = json.loads((mbi / "manifest.json").read_text(encoding="utf-8"))
    mbi_sparse_manifest = json.loads((mbi_sparse / "manifest.json").read_text(encoding="utf-8"))
    rr_manifest = json.loads((rr / "manifest.json").read_text(encoding="utf-8"))
    oma_observation = json.loads((oma / "metadata" / "observation.json").read_text(encoding="utf-8"))
    mbi_observation = json.loads((mbi / "metadata" / "observation.json").read_text(encoding="utf-8"))
    mbi_sparse_observation = json.loads((mbi_sparse / "metadata" / "observation.json").read_text(encoding="utf-8"))
    rr_observation = json.loads((rr / "metadata" / "observation.json").read_text(encoding="utf-8"))

    assert oma_manifest["research"]["scale"] == "research_scale"
    assert oma_manifest["research"]["benchmark_role"] == "oma_baseline"
    assert oma_manifest["research"]["excitation"] == "deterministic_multisine"
    assert oma_manifest["research"]["noise_level"] == "clean"
    assert oma_manifest["content_summary"]["time_steps"] == 501
    assert oma_manifest["content_summary"]["dof_count"] == 12
    assert oma_observation["physical_channel_count"] == 12
    assert oma_observation["virtual_channel_count"] == 0
    assert mbi_manifest["research"]["scale"] == "research_scale"
    assert mbi_manifest["research"]["benchmark_role"] == "mbi_baseline"
    assert mbi_manifest["research"]["excitation"] == "deterministic_multisine"
    assert mbi_manifest["research"]["noise_level"] == "clean"
    assert mbi_manifest["content_summary"]["time_steps"] == 501
    assert mbi_manifest["content_summary"]["dof_count"] == 32
    assert mbi_observation["physical_channel_count"] == 5
    assert mbi_observation["virtual_channel_count"] == 2
    assert [channel["dof"] for channel in mbi_observation["channels"] if channel["kind"] == "virtual"] == [
        "Theta",
        "Theta",
    ]
    assert mbi_sparse_manifest["research"]["task"] == "mode_completion"
    assert mbi_sparse_manifest["research"]["sensor_density"] == "sparse"
    assert mbi_sparse_manifest["content_summary"]["dof_count"] == 32
    assert mbi_sparse_observation["physical_channel_count"] == 3
    assert mbi_sparse_observation["virtual_channel_count"] == 2
    assert rr_manifest["research"]["task"] == "response_reconstruction"
    assert rr_manifest["research"]["sensor_density"] == "sparse"
    assert rr_manifest["content_summary"]["dof_count"] == 12
    assert rr_observation["physical_channel_count"] == 4
    assert rr_observation["virtual_channel_count"] == 0
    assert {channel["kind"] for channel in rr_observation["channels"]} == {"physical"}


def test_stochastic_research_cases_are_reproducible_and_variable(tmp_path: Path) -> None:
    case = json.loads((RESEARCH_CONFIG_ROOT / "oma_shear_12story_stochastic.json").read_text(encoding="utf-8"))
    same_seed = json.loads(json.dumps(case))
    different_seed = json.loads(json.dumps(case))
    different_seed["model_config"]["ground_motion"]["stochastic"]["seed"] = 4102

    first = generate_research_dataset(case, tmp_path / "first")
    second = generate_research_dataset(same_seed, tmp_path / "second")
    third = generate_research_dataset(different_seed, tmp_path / "third")

    with (
        np.load(first / "truth" / "response.npz") as first_response,
        np.load(second / "truth" / "response.npz") as second_response,
        np.load(third / "truth" / "response.npz") as third_response,
        np.load(first / "truth" / "matrices.npz") as first_matrices,
        np.load(third / "truth" / "matrices.npz") as third_matrices,
        np.load(first / "truth" / "modal.npz") as first_modal,
        np.load(third / "truth" / "modal.npz") as third_modal,
    ):
        assert np.allclose(first_response["ground_acceleration"], second_response["ground_acceleration"])
        assert np.allclose(first_response["relative_acceleration"], second_response["relative_acceleration"])
        assert not np.allclose(first_response["ground_acceleration"], third_response["ground_acceleration"])
        assert not np.allclose(first_response["relative_acceleration"], third_response["relative_acceleration"])
        assert np.allclose(first_matrices["mass_matrix"], third_matrices["mass_matrix"])
        assert np.allclose(first_matrices["stiffness_matrix"], third_matrices["stiffness_matrix"])
        assert np.allclose(first_modal["frequency_hz"], third_modal["frequency_hz"])

    first_manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
    first_provenance = json.loads((first / "metadata" / "provenance.json").read_text(encoding="utf-8"))
    assert first_manifest["research"]["excitation"] == "stochastic"
    assert first_manifest["excitation"] == {
        "type": "stochastic",
        "dt": 0.01,
        "duration": 5.0,
        "seed": 4101,
        "source": "generated_stochastic",
    }
    assert first_provenance["random_seed"] == 4101
    assert first_provenance["excitation"] == first_manifest["excitation"]
    assert first_manifest["content_summary"]["physical_channel_count"] == 12


def test_stochastic_oma_beam_case_exports_only_u_physical_observations(tmp_path: Path) -> None:
    output = generate_research_dataset(
        RESEARCH_CONFIG_ROOT / "oma_timoshenko_12story_stochastic.json",
        tmp_path / "oma_beam",
    )
    observation = json.loads((output / "metadata" / "observation.json").read_text(encoding="utf-8"))
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["research"]["task"] == "oma"
    assert manifest["research"]["excitation"] == "stochastic"
    assert observation["physical_channel_count"] == 12
    assert observation["virtual_channel_count"] == 2
    assert {channel["dof"] for channel in observation["channels"] if channel["kind"] == "virtual"} == {"Theta"}
    assert {channel["direction"] for channel in observation["channels"] if channel["kind"] == "physical"} == {"X"}


def test_generate_research_cases_writes_collection_manifest(tmp_path: Path) -> None:
    selected = ["mbi_euler_3story_sparse", "oma_shear_3story"]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        generate_research_cases(tmp_path / "research", selected)

    manifest = json.loads((tmp_path / "research" / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["index_type"] == "research_dataset_collection"
    assert manifest["schema_version"] == "1.0"
    assert manifest["dataset_count"] == 2
    assert [entry["name"] for entry in manifest["datasets"]] == [
        "mbi_euler_3story_sparse",
        "oma_shear_3story",
    ]
    euler = manifest["datasets"][0]
    shear = manifest["datasets"][1]
    assert euler["path"] == "mbi_euler_3story_sparse"
    assert euler["research"] == {
        "task": "mode_completion",
        "family": "euler",
        "sensor_density": "sparse",
        "scale": "small_regression",
    }
    assert euler["noise"] == {
        "configured": False,
        "seed": None,
        "type": "none",
        "target": "physical",
        "level": {"mode": "std_ratio", "value": 0.0},
        "config": {},
    }
    assert euler["content_summary"]["derived_quantity_ids"] == [
        "inter_story_displacement_u",
        "inter_story_drift_ratio_u",
        "story_rotation_difference",
    ]
    assert euler["truth"]["dof_count"] == 6
    assert euler["observations"]["physical_channel_count"] > 0
    assert euler["derived"]["quantity_count"] == 3
    assert shear["research"]["task"] == "oma"
    assert validate_research_dataset_collection(tmp_path / "research") == {
        "index_type": "research_dataset_collection",
        "dataset_count": 2,
        "datasets": ["mbi_euler_3story_sparse", "oma_shear_3story"],
    }


def test_research_dataset_collection_manifest_is_reproducible(tmp_path: Path) -> None:
    selected = ["oma_shear_3story", "mbi_shear_3story_sparse"]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        generate_research_cases(tmp_path / "first", selected)
        generate_research_cases(tmp_path / "second", selected)

    assert (tmp_path / "first" / "manifest.json").read_text(encoding="utf-8") == (
        tmp_path / "second" / "manifest.json"
    ).read_text(encoding="utf-8")


def test_cli_generate_research_cases_runs_selected_case(tmp_path: Path, capsys) -> None:
    output_root = tmp_path / "research_cases_cli"

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        exit_code = cli_main([
            "generate-research-cases",
            "--output-root",
            str(output_root),
            "--case",
            "oma_shear_3story",
            "--validate",
        ])

    assert exit_code == 0
    assert (output_root / "oma_shear_3story" / "manifest.json").exists()
    assert (output_root / "manifest.json").exists()
    captured = capsys.readouterr().out
    assert "oma_shear_3story" in captured
    assert "index_type: research_dataset_collection" in captured


def _csv_header(path: Path) -> list[str]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return next(csv.reader(handle))


def _csv_matrix(path: Path) -> np.ndarray:
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        next(reader)
        return np.asarray([[float(value) for value in row] for row in reader], dtype=float)


def _text_matrix(path: Path) -> np.ndarray:
    return np.loadtxt(path)
