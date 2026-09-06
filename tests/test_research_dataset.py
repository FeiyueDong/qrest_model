from __future__ import annotations

import csv
import json
import warnings
from pathlib import Path

import numpy as np
import pytest

from qrest_model.cli import main as cli_main
from qrest_model.datasets.cases import RESEARCH_CONFIG_ROOT, research_cases, schema_model_type
from qrest_model.datasets.research import generate_research_cases, generate_research_dataset
from qrest_model.datasets.validation import validate_research_dataset, validate_research_dataset_collection
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

    assert manifest["dataset_type"] == "research"
    assert manifest["model_type"] == "euler_beam_2d"
    assert manifest["deterministic"] is True
    assert manifest["config_hash_sha256"] == provenance["config_hash_sha256"]
    assert manifest["derived"] == {"directory": "derived", "structural": "structural.npz"}
    assert manifest["metadata"]["derived"] == "metadata/derived.json"
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
        "oma_euler_3story",
        "oma_timoshenko_3story",
        "mbi_shear_3story_sparse",
        "mbi_euler_3story_sparse",
        "mbi_rigid_3story_sparse",
        "mbi_rayleigh_3story_sparse",
        "mbi_timoshenko_3story_sparse",
        "mbi_shear_flexure_3story_sparse",
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


def test_generate_research_cases_runs_all_configured_cases(tmp_path: Path) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        generated = generate_research_cases(tmp_path / "research")

    assert {path.name for path in generated} == {
        "oma_shear_3story",
        "oma_euler_3story",
        "oma_timoshenko_3story",
        "mbi_shear_3story_sparse",
        "mbi_euler_3story_sparse",
        "mbi_rigid_3story_sparse",
        "mbi_rayleigh_3story_sparse",
        "mbi_timoshenko_3story_sparse",
        "mbi_shear_flexure_3story_sparse",
    }
    assert (tmp_path / "research" / "manifest.json").exists()
    for path in generated:
        summary = validate_research_dataset(path)
        assert summary["name"] == path.name
        assert summary["physical_channel_count"] > 0
    collection = validate_research_dataset_collection(tmp_path / "research")
    assert collection["dataset_count"] == 9


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
    }
    assert euler["noise"] == {"configured": False, "config": {}}
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
