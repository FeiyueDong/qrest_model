"""OpenSeesPy backend for two-dimensional shear-flexure building models."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from qrest_model.analysis.modal import modal_analysis
from qrest_model.analysis.result import AnalysisMetadata, AnalysisResult, ResponseHistory
from qrest_model.common.damping import rayleigh_coefficients
from qrest_model.common.ground_motion import load_ground_motion
from qrest_model.common.opensees import import_opensees
from qrest_model.common.provenance import opensees_provenance
from qrest_model.common.response import add_absolute_beam_response
from qrest_model.exporters.backend_outputs import write_beam2d_outputs
from qrest_model.models.shear_flexure import ShearFlexureBuilding2DModel
from qrest_model.observations.beam import build_beam_sensor_result
from qrest_model.schema import ShearFlexureModelConfig, load_shear_flexure_config
from qrest_model.theory.shear_flexure import base_excitation_influence, base_excitation_load_vector


def run(config: ShearFlexureModelConfig | str | Path, output_dir: str | Path | None = None) -> dict[str, Any]:
    result = run_result(config)
    if output_dir is not None:
        write_outputs(result, output_dir)
    return result.to_legacy_dict()


def run_result(config: ShearFlexureModelConfig | str | Path) -> AnalysisResult:
    ops = import_opensees()
    if not isinstance(config, ShearFlexureModelConfig):
        config_path = Path(config)
        model_config = load_shear_flexure_config(config_path)
        base_dir = config_path.parent
    else:
        model_config = config
        base_dir = Path(".")

    ground = load_ground_motion(model_config.ground_motion, base_dir)
    structural_model = ShearFlexureBuilding2DModel.from_config(model_config)
    mass = structural_model.mass_matrix()
    stiffness = structural_model.stiffness_matrix()
    alpha, beta = rayleigh_coefficients(mass, stiffness, model_config.damping)
    response = _run_opensees(ops, model_config, ground, alpha, beta)
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
        mass_matrix=mass,
        stiffness_matrix=stiffness,
        damping_matrix=alpha * mass + beta * stiffness,
        modal=modal_analysis(mass, stiffness),
        metadata=AnalysisMetadata(
            backend="opensees_shear_flexure",
            response_definition=(
                "OpenSees elasticBeamColumn plus horizontal twoNodeLink response for shear-flexure [u, theta] DOFs; "
                "absolute u/v/a include horizontal ground translation while theta remains bending rotation"
            ),
            rayleigh_alpha=alpha,
            rayleigh_beta=beta,
            extras=opensees_provenance() | {
                "model_type": model_config.model_type,
                "dof_per_floor": list(model_config.dof_per_floor),
                "opensees_frequency_hz": response["opensees_frequency_hz"].tolist(),
                "ground_displacement_source": response["ground_displacement_source"],
                "ground_velocity_source": response["ground_velocity_source"],
            },
        ),
        story_stiffness_rows=_story_rows(model_config),
    )


def _run_opensees(
    ops: Any,
    config: ShearFlexureModelConfig,
    ground: dict[str, np.ndarray],
    rayleigh_alpha: float,
    rayleigh_beta: float,
) -> dict[str, np.ndarray]:
    ops.wipe()
    ops.model("basic", "-ndm", 2, "-ndf", 3)

    base_tag = 1
    ops.node(base_tag, 0.0, 0.0)
    ops.fix(base_tag, 1, 1, 1)

    node_tags = []
    for story, elevation in enumerate(config.geometry.elevations, start=1):
        tag = 1000 + story
        node_tags.append(tag)
        ops.node(tag, 0.0, elevation)
        ops.fix(tag, 0, 1, 0)

    transf_tag = 1
    ops.geomTransf("Linear", transf_tag)
    for story in config.stories:
        section = story.flexural_section
        lower = base_tag if story.story == 1 else 1000 + story.story - 1
        upper = 1000 + story.story
        mass_per_length = section.density * section.A
        ops.element(
            "elasticBeamColumn",
            story.story,
            lower,
            upper,
            section.A,
            section.E,
            section.I,
            transf_tag,
            "-mass",
            mass_per_length,
            "-cMass",
        )
        if story.shear_stiffness > 0.0:
            mat_tag = 2000 + story.story
            link_tag = 3000 + story.story
            ops.uniaxialMaterial("Elastic", mat_tag, story.shear_stiffness)
            ops.element(
                "twoNodeLink",
                link_tag,
                lower,
                upper,
                "-mat",
                mat_tag,
                "-dir",
                1,
                "-orient",
                1.0,
                0.0,
                0.0,
                0.0,
                1.0,
                0.0,
                "-doRayleigh",
            )

    opensees_frequency = _modal_frequency_hz(ops, 2 * config.num_stories)

    dt = float(ground["time"][1] - ground["time"][0])
    ops.timeSeries("Path", 1, "-dt", dt, "-values", *ground["ax"].tolist(), "-useLast")
    ops.pattern("Plain", 1, 1)
    load_mass = base_excitation_load_vector(config.stories, config.geometry)
    for story_index, tag in enumerate(node_tags):
        u_load = -load_mass[2 * story_index]
        theta_load = -load_mass[2 * story_index + 1]
        ops.load(tag, u_load, 0.0, -theta_load)
    ops.constraints("Plain")
    ops.numberer("RCM")
    ops.system("BandGeneral")
    ops.test("NormDispIncr", 1.0e-10, 10)
    ops.algorithm("Linear")
    ops.integrator("Newmark", 0.5, 0.25)
    ops.rayleigh(rayleigh_alpha, rayleigh_beta, 0.0, 0.0)
    ops.analysis("Transient")
    initial_accel = -base_excitation_influence(config.stories, config.geometry) * float(ground["ax"][0])
    for story_index, tag in enumerate(node_tags):
        ops.setNodeAccel(tag, 1, initial_accel[2 * story_index], "-commit")
        ops.setNodeAccel(tag, 3, -initial_accel[2 * story_index + 1], "-commit")

    n_steps = ground["time"].size
    disp = np.zeros((n_steps, config.num_stories, 2), dtype=float)
    vel = np.zeros_like(disp)
    acc = np.zeros_like(disp)
    for step in range(n_steps):
        if step > 0:
            ok = ops.analyze(1, dt)
            if ok != 0:
                raise RuntimeError(f"OpenSees shear-flexure analysis failed at step {step} with code {ok}.")
        for story_index, tag in enumerate(node_tags):
            disp[step, story_index, 0] = ops.nodeDisp(tag, 1)
            disp[step, story_index, 1] = -ops.nodeDisp(tag, 3)
            vel[step, story_index, 0] = ops.nodeVel(tag, 1)
            vel[step, story_index, 1] = -ops.nodeVel(tag, 3)
            acc[step, story_index, 0] = ops.nodeAccel(tag, 1)
            acc[step, story_index, 1] = -ops.nodeAccel(tag, 3)
    return {
        "time": ground["time"],
        "displacement": disp,
        "velocity": vel,
        "acceleration": acc,
        "opensees_frequency_hz": opensees_frequency,
    }


def _modal_frequency_hz(ops: Any, mode_count: int) -> np.ndarray:
    eigenvalues = np.asarray(ops.eigen("-fullGenLapack", mode_count), dtype=float)
    if np.any(eigenvalues <= 0.0):
        raise ValueError("OpenSees shear-flexure eigenvalues must be positive.")
    return np.sqrt(eigenvalues) / (2.0 * np.pi)


def _story_rows(config: ShearFlexureModelConfig) -> list[dict[str, Any]]:
    return [
        {
            "story": story.story,
            "height": config.geometry.story_heights[story.story - 1],
            "E": story.flexural_section.E,
            "A": story.flexural_section.A,
            "I": story.flexural_section.I,
            "density": story.flexural_section.density,
            "shear_stiffness": story.shear_stiffness,
        }
        for story in config.stories
    ]


def write_outputs(result: AnalysisResult | dict[str, Any], output_dir: str | Path) -> None:
    write_beam2d_outputs(result, output_dir)


__all__ = ["run", "run_result", "write_outputs"]
