from __future__ import annotations

import os

import numpy as np
import pytest

from qrest_model.backends import run_analysis
from qrest_model.backends.opensees_support_motion import run_shear_imposed_support_result


def _require_opensees_tests() -> None:
    if os.environ.get("QREST_RUN_OPENSEES_TESTS") != "1":
        pytest.skip("Set QREST_RUN_OPENSEES_TESTS=1 to run OpenSeesPy validation.")


def _undamped_two_story_shear_raw() -> dict:
    return {
        "schema_version": "2.0",
        "model": {
            "type": "shear_building_1d",
            "num_stories": 2,
            "dof_per_floor": ["Ux"],
        },
        "floor_defaults": {
            "mass": 1.0e6,
        },
        "stories": [
            {"story": 1, "stiffness": 7.0e8},
            {"story": 2, "stiffness": 5.0e8},
        ],
        "sensors": [
            {"id": "01f_x", "story": 1, "quantity": "accel"},
            {"id": "02f_x", "story": 2, "quantity": "accel"},
        ],
        "damping": {"type": "rayleigh", "zeta": 0.0, "modes": [1, 2]},
        "ground_motion": {
            "dt": 0.005,
            "duration": 0.25,
            "synthetic": {
                "amplitude_x": 0.12,
                "frequency_x": 1.3,
                "decay": 0.02,
            },
        },
    }


@pytest.mark.opensees
def test_opensees_imposed_support_motion_matches_direct_equivalent_excitation() -> None:
    _require_opensees_tests()
    raw = _undamped_two_story_shear_raw()

    direct = run_analysis(raw, backend="direct")
    imposed = run_shear_imposed_support_result(raw)

    assert imposed.metadata.backend == "opensees_shear_imposed_support"
    assert imposed.metadata.extras["base_excitation_source"] == "OpenSees MultipleSupport imposedMotion"
    assert imposed.metadata.extras["response_source"] == "opensees_imposed_support_motion"
    assert np.allclose(direct.mass_matrix, imposed.mass_matrix)
    assert np.allclose(direct.stiffness_matrix, imposed.stiffness_matrix)
    assert np.allclose(direct.relative.displacement, imposed.relative.displacement, atol=1.0e-10, rtol=1.0e-7)
    assert np.allclose(direct.relative.velocity, imposed.relative.velocity, atol=1.0e-9, rtol=1.0e-7)
    assert np.allclose(direct.relative.acceleration, imposed.relative.acceleration, atol=1.0e-8, rtol=1.0e-7)
    assert np.allclose(direct.absolute.acceleration, imposed.absolute.acceleration, atol=1.0e-8, rtol=1.0e-7)
