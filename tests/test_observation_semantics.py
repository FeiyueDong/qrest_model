from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pytest

from qrest_model.backends.base import run_analysis
from qrest_model.observations import PHYSICAL, VIRTUAL, ObservationResult, quantity_unit
from qrest_model.exporters.qrest_dataset import export_dataset
from qrest_model.exporters.qrest_metadata import build_qrest_metadata
from qrest_model.analysis.result import AnalysisMetadata, AnalysisResult, ResponseHistory
from qrest_model.schema import normalize_config, normalize_euler_config


MODEL_ROOT = Path(__file__).resolve().parents[1]


def test_legacy_beam_theta_sensor_is_virtual_probe() -> None:
    raw = json.loads((MODEL_ROOT / "beam2d/configs/euler_3story.json").read_text(encoding="utf-8"))

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        config = normalize_euler_config(raw)

    assert [sensor.kind for sensor in config.sensors] == ["physical", "virtual"]
    result = run_analysis(config, backend="direct")
    assert result.observations is result.sensors
    assert [channel.kind for channel in result.observations.channels] == ["physical", "virtual"]
    assert result.observations.channels[1].dof == "Theta"
    assert result.observations.channels[1].unit == "rad"


def test_observation_public_api_exposes_units_and_result_validation() -> None:
    assert PHYSICAL == "physical"
    assert VIRTUAL == "virtual"
    assert quantity_unit("accel", axis="translation") == "m/s^2"
    assert quantity_unit("velocity", axis="rotation") == "rad/s"

    channel = result_channel("physical_u")
    with pytest.raises(ValueError, match="one array per channel"):
        ObservationResult(channels=(channel,), displacement=())


def test_analysis_result_keeps_sensors_and_observations_as_compatibility_aliases() -> None:
    channel = result_channel("physical_u")
    observations = ObservationResult(channels=(channel,), acceleration=(np.zeros(3),))
    history = ResponseHistory(
        displacement=np.zeros((3, 1)),
        velocity=np.zeros((3, 1)),
        acceleration=np.zeros((3, 1)),
    )

    result = AnalysisResult(
        time=np.array([0.0, 0.1, 0.2]),
        relative=history,
        mass_matrix=np.eye(1),
        stiffness_matrix=np.eye(1),
        damping_matrix=np.zeros((1, 1)),
        metadata=AnalysisMetadata(backend="test", response_definition="test"),
        observations=observations,
    )

    assert result.sensors is not None
    assert result.sensors.channels == observations.channels
    assert result.to_legacy_dict()["sensor_rows"] == []


def test_explicit_physical_theta_and_rz_are_rejected() -> None:
    beam = json.loads((MODEL_ROOT / "beam2d/configs/euler_3story.json").read_text(encoding="utf-8"))
    beam["sensors"] = [{"id": "bad_theta", "kind": "physical", "story": 3, "dof": "Theta"}]
    with pytest.raises(ValueError, match="Physical translation sensors cannot use generalized Theta"):
        normalize_euler_config(beam)

    rigid = _rigid_config()
    rigid["sensors"] = [{"id": "bad_rz", "kind": "physical", "story": 1, "direction": "RZ"}]
    with pytest.raises(ValueError, match="Physical translation sensors cannot use structural Rz"):
        normalize_config(rigid)


def test_qrest_metadata_exports_only_physical_observations() -> None:
    raw = json.loads((MODEL_ROOT / "beam2d/configs/euler_3story.json").read_text(encoding="utf-8"))

    metadata = build_qrest_metadata(raw, npts=11)

    channels = metadata["InstrumentInfo"]["Channels"]
    assert metadata["InstrumentInfo"]["ChannelNum"] == 1
    assert [channel["ChannelID"] for channel in channels] == ["roof_u"]
    assert channels[0]["Azimuth"] == 90.0


def test_qrest_metadata_rejects_explicit_physical_generalized_dof() -> None:
    raw = json.loads((MODEL_ROOT / "beam2d/configs/euler_3story.json").read_text(encoding="utf-8"))
    raw["sensors"] = [{"id": "bad_theta", "kind": "physical", "story": 3, "dof": "Theta"}]

    with pytest.raises(ValueError, match="cannot be exported as a qREST physical channel"):
        build_qrest_metadata(raw, npts=11)


def test_qrest_dataset_uses_physical_metadata_subset(tmp_path: Path) -> None:
    generated_dir = tmp_path / "generated_case"
    time_history_dir = generated_dir / "time_history"
    time_history_dir.mkdir(parents=True)
    config = {
        "model": {"num_stories": 1},
        "geometry": {"story_heights": [3.0]},
        "sensors": [
            {"id": "physical_u", "kind": "physical", "story": 1, "dof": "U", "quantity": "accel"},
            {"id": "virtual_theta", "kind": "virtual", "story": 1, "dof": "Theta", "quantity": "accel"},
        ],
        "ground_motion": {"dt": 0.02, "duration": 0.02},
    }
    metadata = build_qrest_metadata(config, npts=2)
    (generated_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    (time_history_dir / "acceleration.csv").write_text(
        "time,physical_u,virtual_theta\n0.0,1.0,9.0\n0.02,2.0,10.0\n",
        encoding="utf-8",
    )

    exported = export_dataset(generated_dir, tmp_path / "qrest_case", config_source=None)

    assert (exported / "qrest_case_data.txt").read_text(encoding="utf-8") == "1.0\n2.0\n"


def test_truth_is_independent_of_observation_layout() -> None:
    raw_a = _rigid_config()
    raw_b = _rigid_config()
    raw_b["sensors"] = [
        {"id": "story1_y", "story": 1, "x": 1.0, "y": 0.0, "direction": "Y"},
        {"id": "story2_x", "story": 2, "x": 0.0, "y": -1.0, "direction": "X"},
    ]

    result_a = run_analysis(raw_a, backend="direct")
    result_b = run_analysis(raw_b, backend="direct")

    assert np.allclose(result_a.mass_matrix, result_b.mass_matrix)
    assert np.allclose(result_a.stiffness_matrix, result_b.stiffness_matrix)
    assert np.allclose(result_a.modal.frequency, result_b.modal.frequency)
    assert np.allclose(result_a.relative.acceleration, result_b.relative.acceleration)
    assert result_a.sensors.rows != result_b.sensors.rows


def _rigid_config() -> dict:
    return {
        "schema_version": "2.0",
        "model": {
            "type": "rigid_floor_shear_3d",
            "num_stories": 2,
            "dof_per_floor": ["Ux", "Uy", "Rz"],
            "coordinate_reference": "geometry_center",
        },
        "floor_defaults": {
            "mass": 1.0e6,
            "jz": 8.0e6,
            "mass_center": [0.0, 0.0],
            "direct_stiffness": {
                "kx": 8.0e8,
                "ky": 8.0e8,
                "ktheta": 2.5e10,
                "stiffness_center": [0.0, 0.0],
            },
        },
        "stories": [{"story": 1}, {"story": 2}],
        "sensors": [{"id": "story1_x", "story": 1, "x": 0.0, "y": 0.0, "direction": "X"}],
        "damping": {"type": "rayleigh", "zeta": 0.02, "modes": [1, 3]},
        "ground_motion": {
            "dt": 0.02,
            "duration": 0.10,
            "synthetic": {"amplitude_x": 0.1, "amplitude_y": 0.05},
        },
    }


def result_channel(observation_id: str):
    from qrest_model.observations import physical_channel

    return physical_channel(
        observation_id,
        story=1,
        quantity="accel",
        direction="X",
    )
