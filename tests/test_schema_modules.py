from __future__ import annotations

from qrest_model import schema
from qrest_model.schema import beam_common, euler, geometry, rayleigh, rigid_floor, shear_building, shear_flexure, timoshenko


def test_schema_submodules_reexport_canonical_model_entry_points() -> None:
    assert geometry.GeometryConfig is schema.GeometryConfig
    assert geometry.normalize_geometry is schema.normalize_geometry
    assert beam_common.BeamSectionConfig is schema.BeamSectionConfig
    assert beam_common.BeamSensorConfig is schema.BeamSensorConfig

    assert rigid_floor.ModelConfig is schema.ModelConfig
    assert rigid_floor.normalize_config is schema.normalize_config
    assert rigid_floor.load_config is schema.load_config

    assert shear_building.ShearModelConfig is schema.ShearModelConfig
    assert shear_building.normalize_shear_config is schema.normalize_shear_config
    assert shear_building.load_shear_config is schema.load_shear_config

    assert euler.EulerBeamModelConfig is schema.EulerBeamModelConfig
    assert euler.normalize_euler_config is schema.normalize_euler_config
    assert euler.load_euler_config is schema.load_euler_config

    assert rayleigh.RayleighBeamModelConfig is schema.RayleighBeamModelConfig
    assert rayleigh.normalize_rayleigh_config is schema.normalize_rayleigh_config
    assert rayleigh.load_rayleigh_config is schema.load_rayleigh_config

    assert timoshenko.TimoshenkoBeamModelConfig is schema.TimoshenkoBeamModelConfig
    assert timoshenko.normalize_timoshenko_config is schema.normalize_timoshenko_config
    assert timoshenko.load_timoshenko_config is schema.load_timoshenko_config

    assert shear_flexure.ShearFlexureModelConfig is schema.ShearFlexureModelConfig
    assert shear_flexure.normalize_shear_flexure_config is schema.normalize_shear_flexure_config
    assert shear_flexure.load_shear_flexure_config is schema.load_shear_flexure_config
    assert schema.ObservationConfig
    assert schema.PhysicalObservationConfig
    assert schema.VirtualProbeConfig
