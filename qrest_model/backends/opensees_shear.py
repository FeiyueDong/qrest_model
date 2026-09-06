"""OpenSeesPy backend for one-direction shear-building models."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from qrest_model.analysis.modal import modal_analysis
from qrest_model.analysis.result import AnalysisMetadata, AnalysisResult, ResponseHistory, SensorResult
from qrest_model.common.damping import rayleigh_coefficients
from qrest_model.common.ground_motion import load_ground_motion
from qrest_model.common.opensees import import_opensees
from qrest_model.common.provenance import opensees_provenance
from qrest_model.common.response import add_absolute_shear_response
from qrest_model.schema import ShearModelConfig, load_shear_config
from qrest_model.exporters.backend_outputs import write_shear_outputs
from qrest_model.models.shear_building import ShearBuildingModel
from qrest_model.observations.shear import build_shear_sensor_result
from qrest_model.theory.shear_stiffness import (
    shear_story_stiffness_table,
)


def run(config: ShearModelConfig | str | Path, output_dir: str | Path | None = None) -> dict[str, Any]:
    result = run_result(config)
    if output_dir is not None:
        write_outputs(result, output_dir)
    return result.to_legacy_dict()


def run_result(config: ShearModelConfig | str | Path) -> AnalysisResult:
    ops = import_opensees()
    if not isinstance(config, ShearModelConfig):
        config_path = Path(config)
        model_config = load_shear_config(config_path)
        base_dir = config_path.parent
    else:
        model_config = config
        base_dir = Path(".")

    ground = load_ground_motion(model_config.ground_motion, base_dir)
    ground_accel = ground["ax"] if model_config.direction == "X" else ground["ay"]
    structural_model = ShearBuildingModel.from_config(model_config)
    mass = structural_model.mass_matrix()
    stiffness = structural_model.stiffness_matrix()
    alpha, beta = rayleigh_coefficients(mass, stiffness, model_config.damping)
    response = _run_opensees(
        ops, model_config, ground["time"], ground_accel, alpha, beta)
    add_absolute_shear_response(response, ground["ax"], ground["ay"], model_config.direction)
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
        sensors=build_shear_sensor_result(model_config.sensors, response, direction=model_config.direction),
        mass_matrix=mass,
        stiffness_matrix=stiffness,
        damping_matrix=alpha * mass + beta * stiffness,
        modal=modal_analysis(mass, stiffness),
        metadata=AnalysisMetadata(
            backend="opensees_shear",
            response_definition=(
                "OpenSees UniformExcitation one-direction response; relative is node response, "
                "absolute includes the selected ground translation component"
            ),
            rayleigh_alpha=alpha,
            rayleigh_beta=beta,
            extras=opensees_provenance() | {
                "direction": model_config.direction,
                "ground_displacement_source": response["ground_displacement_source"],
                "ground_velocity_source": response["ground_velocity_source"],
            },
        ),
        story_stiffness_rows=shear_story_stiffness_table(model_config.stories),
    )


def _run_opensees(
    ops: Any,
    config: ShearModelConfig,
    time: np.ndarray,
    ground_accel: np.ndarray,
    rayleigh_alpha: float,
    rayleigh_beta: float,
) -> dict[str, np.ndarray]:
    ops.wipe()
    ops.model("basic", "-ndm", 1, "-ndf", 1)

    ground_tag = 1
    ops.node(ground_tag, 0.0)
    ops.fix(ground_tag, 1)

    node_tags = []
    for story in config.stories:
        tag = 1000 + story.story
        node_tags.append(tag)
        ops.node(tag, 0.0)
        ops.mass(tag, story.mass)

    for story in config.stories:
        mat_tag = story.story
        ele_tag = story.story
        lower = ground_tag if story.story == 1 else 1000 + story.story - 1
        upper = 1000 + story.story
        ops.uniaxialMaterial("Elastic", mat_tag, story.stiffness)
        ops.element("zeroLength", ele_tag, lower,
                    upper, "-mat", mat_tag, "-dir", 1, "-doRayleigh", 1)

    dt = float(time[1] - time[0])
    ops.timeSeries("Path", 1, "-dt", dt, "-values", *ground_accel.tolist(), "-useLast")
    ops.pattern("UniformExcitation", 1, 1, "-accel", 1)
    ops.constraints("Plain")
    ops.numberer("RCM")
    ops.system("BandGeneral")
    ops.test("NormDispIncr", 1.0e-10, 10)
    ops.algorithm("Linear")
    ops.integrator("Newmark", 0.5, 0.25)
    ops.rayleigh(rayleigh_alpha, rayleigh_beta, 0.0, 0.0)
    ops.analysis("Transient")
    initial_accel = -float(ground_accel[0])
    for story in config.stories:
        ops.setNodeAccel(1000 + story.story, 1, initial_accel, "-commit")

    n_steps = time.size
    n = config.num_stories
    disp = np.zeros((n_steps, n), dtype=float)
    vel = np.zeros_like(disp)
    acc = np.zeros_like(disp)
    for step in range(n_steps):
        if step > 0:
            ok = ops.analyze(1, dt)
            if ok != 0:
                raise RuntimeError(
                    f"OpenSees shear analysis failed at step {step} with code {ok}.")
        for i, tag in enumerate(node_tags):
            disp[step, i] = ops.nodeDisp(tag, 1)
            vel[step, i] = ops.nodeVel(tag, 1)
            acc[step, i] = ops.nodeAccel(tag, 1)
    return {"time": time, "displacement": disp, "velocity": vel, "acceleration": acc}


def write_outputs(result: AnalysisResult | dict[str, Any], output_dir: str | Path) -> None:
    write_shear_outputs(result, output_dir)
