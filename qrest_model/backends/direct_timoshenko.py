"""Direct backend for two-dimensional Timoshenko beam models."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from qrest_model.analysis.result import AnalysisMetadata, AnalysisResult, ResponseHistory
from qrest_model.backends.direct_linear import run_linear_direct
from qrest_model.common.ground_motion import load_ground_motion
from qrest_model.common.provenance import direct_provenance
from qrest_model.common.response import add_absolute_beam_response
from qrest_model.exporters.backend_outputs import write_beam2d_outputs
from qrest_model.models.timoshenko_beam import TimoshenkoBeam2DModel
from qrest_model.observations.beam import build_beam_sensor_result
from qrest_model.schema import TimoshenkoBeamModelConfig, load_timoshenko_config


def run(config: TimoshenkoBeamModelConfig | str | Path, output_dir: str | Path | None = None) -> dict[str, Any]:
    result = run_result(config)
    if output_dir is not None:
        write_outputs(result, output_dir)
    return result.to_legacy_dict()


def run_result(config: TimoshenkoBeamModelConfig | str | Path) -> AnalysisResult:
    if not isinstance(config, TimoshenkoBeamModelConfig):
        config_path = Path(config)
        model_config = load_timoshenko_config(config_path)
        base_dir = config_path.parent
    else:
        model_config = config
        base_dir = Path(".")

    ground = load_ground_motion(model_config.ground_motion, base_dir)
    structural_model = TimoshenkoBeam2DModel.from_config(model_config)
    linear = run_linear_direct(
        structural_model,
        model_config.damping,
        ground["time"],
        ground["ax"],
    )
    n_steps = linear.time.size
    response = {
        "time": linear.time,
        "displacement": linear.displacement.reshape((n_steps, model_config.num_stories, 2)),
        "velocity": linear.velocity.reshape((n_steps, model_config.num_stories, 2)),
        "acceleration": linear.acceleration.reshape((n_steps, model_config.num_stories, 2)),
    }
    add_absolute_beam_response(response, ground["ax"], ground["ay"])
    return AnalysisResult(
        time=response["time"],
        relative=ResponseHistory(
            displacement=response["displacement"],
            velocity=response["velocity"],
            acceleration=response["acceleration"],
        ),
        absolute=ResponseHistory(
            displacement=response["absolute_displacement"],
            velocity=response["absolute_velocity"],
            acceleration=response["absolute_acceleration"],
        ),
        ground=ResponseHistory(
            displacement=response["ground_displacement"],
            velocity=response["ground_velocity"],
            acceleration=response["ground_acceleration"],
        ),
        sensors=build_beam_sensor_result(model_config.sensors, response),
        mass_matrix=linear.mass_matrix,
        stiffness_matrix=linear.stiffness_matrix,
        damping_matrix=linear.damping_matrix,
        modal=linear.modal,
        metadata=AnalysisMetadata(
            backend="direct_timoshenko",
            response_definition=(
                "u/theta, v/vtheta, a/atheta are relative Timoshenko beam response; "
                "absolute u/v/a include horizontal ground translation while theta remains bending rotation"
            ),
            rayleigh_alpha=linear.rayleigh_alpha,
            rayleigh_beta=linear.rayleigh_beta,
            extras=direct_provenance() | {
                "model_type": model_config.model_type,
                "dof_per_floor": list(model_config.dof_per_floor),
                "geometry": {
                    "base_elevation": model_config.geometry.base_elevation,
                    "story_heights": list(model_config.geometry.story_heights),
                    "elevations": list(model_config.geometry.elevations),
                },
                "ground_displacement_source": response["ground_displacement_source"],
                "ground_velocity_source": response["ground_velocity_source"],
            },
        ),
        story_stiffness_rows=_section_rows(model_config),
    )


def _section_rows(config: TimoshenkoBeamModelConfig) -> list[dict[str, Any]]:
    return [
        {
            "story": section.story,
            "height": config.geometry.story_heights[section.story - 1],
            "E": section.E,
            "G": section.G,
            "A": section.A,
            "I": section.I,
            "shear_area": section.shear_area,
            "density": section.density,
        }
        for section in config.sections
    ]


def write_outputs(result: AnalysisResult | dict[str, Any], output_dir: str | Path) -> None:
    write_beam2d_outputs(result, output_dir)


__all__ = ["run", "run_result", "write_outputs"]
