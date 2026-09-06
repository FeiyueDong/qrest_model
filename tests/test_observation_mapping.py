from __future__ import annotations

import numpy as np

from qrest_model.observations.beam import build_beam_sensor_result, build_beam_sensor_rows
from qrest_model.observations.shear import build_shear_sensor_result, build_shear_sensor_rows
from qrest_model.postprocess.sensor_mapping import build_sensor_result as build_rigid_sensor_result
from qrest_model.schema import BeamSensorConfig, SensorConfig, ShearSensorConfig


def test_beam_observation_mapping_is_backend_independent() -> None:
    response = _beam_response()
    sensors = (
        BeamSensorConfig(sensor_id="floor2_u_acc", story=2, dof="U", quantity="accel"),
        BeamSensorConfig(sensor_id="floor1_theta_disp", story=1, dof="Theta", quantity="disp", kind="virtual"),
    )

    mapped = build_beam_sensor_result(sensors, response)
    rows = build_beam_sensor_rows(sensors, response)

    assert mapped.rows == rows
    assert np.allclose(mapped.acceleration[0], response["acceleration"][:, 1, 0])
    assert np.allclose(mapped.displacement[1], response["displacement"][:, 0, 1])
    assert rows[0]["node_or_sensor_id"] == "floor2_u_acc"
    assert rows[0]["observation_kind"] == "physical"
    assert rows[0]["dof"] == "U"
    assert rows[0]["unit"] == "m/s^2"
    assert rows[0]["value"] == response["absolute_acceleration"][0, 1, 0]
    assert rows[-1]["node_or_sensor_id"] == "floor1_theta_disp"
    assert rows[-1]["observation_kind"] == "virtual"
    assert rows[-1]["unit"] == "rad"
    assert rows[-1]["relative_value"] == response["displacement"][-1, 0, 1]
    assert [channel.kind for channel in mapped.channels] == ["physical", "virtual"]
    assert [channel.unit for channel in mapped.channels] == ["m/s^2", "rad"]
    assert mapped.channels[0].operator.to_dict() == {
        "form": "linear_combination",
        "terms": [{"frame": "absolute", "quantity": "acceleration", "story": 2, "dof": "U", "coefficient": 1.0}],
    }
    assert mapped.channels[1].operator.to_dict() == {
        "form": "linear_combination",
        "terms": [{"frame": "relative", "quantity": "displacement", "story": 1, "dof": "Theta", "coefficient": 1.0}],
    }


def test_shear_observation_mapping_is_backend_independent() -> None:
    response = _shear_response()
    sensors = (
        ShearSensorConfig(sensor_id="floor2_u_vel", story=2, quantity="vel"),
        ShearSensorConfig(sensor_id="floor1_u_acc", story=1, quantity="accel"),
    )

    mapped = build_shear_sensor_result(sensors, response, direction="X")
    rows = build_shear_sensor_rows(sensors, response, direction="X")

    assert mapped.rows == rows
    assert np.allclose(mapped.velocity[0], response["velocity"][:, 1])
    assert np.allclose(mapped.acceleration[1], response["acceleration"][:, 0])
    assert rows[0]["observation_kind"] == "physical"
    assert rows[0]["direction"] == "X"
    assert rows[0]["unit"] == "m/s"
    assert rows[0]["value"] == response["absolute_velocity"][0, 1]
    assert rows[-1]["relative_value"] == response["acceleration"][-1, 0]
    assert [channel.kind for channel in mapped.channels] == ["physical", "physical"]
    assert mapped.channels[0].operator.to_dict() == {
        "form": "linear_combination",
        "terms": [{"frame": "absolute", "quantity": "velocity", "story": 2, "dof": "U", "coefficient": 1.0}],
    }


def test_rigid_floor_observation_operator_records_mapping_coefficients() -> None:
    time = np.array([0.0, 0.1, 0.2])
    displacement = np.zeros((3, 1, 3))
    velocity = np.zeros_like(displacement)
    acceleration = np.zeros_like(displacement)
    sensors = (
        SensorConfig(sensor_id="x_at_ypos", story=1, x=0.0, y=3.0, direction="X", quantity="accel"),
        SensorConfig(sensor_id="rz_probe", story=1, x=0.0, y=0.0, direction="RZ", quantity="disp", kind="virtual"),
    )

    mapped = build_rigid_sensor_result(sensors, time, displacement, velocity, acceleration)

    assert mapped.channels[0].operator.to_dict() == {
        "form": "linear_combination",
        "terms": [
            {"frame": "absolute", "quantity": "acceleration", "story": 1, "dof": "Ux", "coefficient": 1.0},
            {"frame": "absolute", "quantity": "acceleration", "story": 1, "dof": "Rz", "coefficient": -3.0},
        ],
    }
    assert mapped.channels[1].operator.to_dict() == {
        "form": "linear_combination",
        "terms": [{"frame": "relative", "quantity": "displacement", "story": 1, "dof": "Rz", "coefficient": 1.0}],
    }


def _beam_response() -> dict[str, np.ndarray]:
    shape = (3, 2, 2)
    relative_displacement = np.arange(12, dtype=float).reshape(shape)
    relative_velocity = relative_displacement + 100.0
    relative_acceleration = relative_displacement + 200.0
    return {
        "time": np.array([0.0, 0.1, 0.2]),
        "displacement": relative_displacement,
        "velocity": relative_velocity,
        "acceleration": relative_acceleration,
        "absolute_displacement": relative_displacement + 1.0,
        "absolute_velocity": relative_velocity + 1.0,
        "absolute_acceleration": relative_acceleration + 1.0,
    }


def _shear_response() -> dict[str, np.ndarray]:
    shape = (3, 2)
    relative_displacement = np.arange(6, dtype=float).reshape(shape)
    relative_velocity = relative_displacement + 100.0
    relative_acceleration = relative_displacement + 200.0
    return {
        "time": np.array([0.0, 0.1, 0.2]),
        "displacement": relative_displacement,
        "velocity": relative_velocity,
        "acceleration": relative_acceleration,
        "absolute_displacement": relative_displacement + 1.0,
        "absolute_velocity": relative_velocity + 1.0,
        "absolute_acceleration": relative_acceleration + 1.0,
    }
