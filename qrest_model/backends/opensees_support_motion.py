"""Independent OpenSees imposed-support validation helpers."""

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
from qrest_model.common.response import ground_kinematics
from qrest_model.models.shear_building import ShearBuildingModel
from qrest_model.models.euler_beam import EulerBeam2DModel
from qrest_model.observations.beam import build_beam_sensor_result
from qrest_model.observations.shear import build_shear_sensor_result
from qrest_model.schema import (
    EulerBeamModelConfig,
    ShearModelConfig,
    load_euler_config,
    load_shear_config,
    normalize_euler_config,
    normalize_shear_config,
)
from qrest_model.theory.shear_stiffness import shear_story_stiffness_table


def run_shear_imposed_support_result(config: ShearModelConfig | str | Path | dict[str, Any]) -> AnalysisResult:
    """Run a shear-building case using true OpenSees imposed support motion.

    This helper is intended for integration validation only. The production
    OpenSees shear backend continues to use UniformExcitation so its response
    definition stays stable.
    """

    ops = import_opensees()
    if isinstance(config, dict):
        model_config = normalize_shear_config(config)
        base_dir = Path(".")
    elif not isinstance(config, ShearModelConfig):
        config_path = Path(config)
        model_config = load_shear_config(config_path)
        base_dir = config_path.parent
    else:
        model_config = config
        base_dir = Path(".")

    ground = load_ground_motion(model_config.ground_motion, base_dir)
    ground_accel = ground["ax"] if model_config.direction == "X" else ground["ay"]
    ground_full = ground_kinematics(ground["time"], ground["ax"], ground["ay"])
    ground_index = 0 if model_config.direction == "X" else 1
    ground_disp = ground_full["displacement"][:, ground_index]
    ground_vel = ground_full["velocity"][:, ground_index]

    structural_model = ShearBuildingModel.from_config(model_config)
    mass = structural_model.mass_matrix()
    stiffness = structural_model.stiffness_matrix()
    alpha, beta = rayleigh_coefficients(mass, stiffness, model_config.damping)
    damping = alpha * mass + beta * stiffness
    response = _run_shear_imposed_support(
        ops,
        model_config,
        ground["time"],
        ground_disp,
        ground_vel,
        ground_accel,
        alpha,
        beta,
    )
    relative = {
        "time": response["time"],
        "displacement": response["absolute_displacement"] - ground_disp[:, None],
        "velocity": response["absolute_velocity"] - ground_vel[:, None],
        "acceleration": response["absolute_acceleration"] - ground_accel[:, None],
        "absolute_displacement": response["absolute_displacement"],
        "absolute_velocity": response["absolute_velocity"],
        "absolute_acceleration": response["absolute_acceleration"],
        "ground_displacement": ground_full["displacement"],
        "ground_velocity": ground_full["velocity"],
        "ground_acceleration": ground_full["acceleration"],
        "ground_displacement_source": "integrated_from_acceleration",
        "ground_velocity_source": "integrated_from_acceleration",
    }
    return AnalysisResult(
        time=relative["time"],
        relative=ResponseHistory(
            displacement=relative["displacement"],
            velocity=relative["velocity"],
            acceleration=relative["acceleration"],
        ),
        absolute=ResponseHistory(
            displacement=relative["absolute_displacement"],
            velocity=relative["absolute_velocity"],
            acceleration=relative["absolute_acceleration"],
        ),
        ground=ResponseHistory(
            displacement=relative["ground_displacement"],
            velocity=relative["ground_velocity"],
            acceleration=relative["ground_acceleration"],
        ),
        sensors=build_shear_sensor_result(model_config.sensors, relative, direction=model_config.direction),
        mass_matrix=mass,
        stiffness_matrix=stiffness,
        damping_matrix=damping,
        modal=modal_analysis(mass, stiffness),
        metadata=AnalysisMetadata(
            backend="opensees_shear_imposed_support",
            response_definition=(
                "OpenSees MultipleSupport imposed support motion; node responses are absolute, "
                "relative response subtracts the imposed base motion"
            ),
            rayleigh_alpha=alpha,
            rayleigh_beta=beta,
            extras=opensees_provenance() | {
                "response_source": "opensees_imposed_support_motion",
                "base_excitation_source": "OpenSees MultipleSupport imposedMotion",
                "direction": model_config.direction,
                "ground_displacement_source": relative["ground_displacement_source"],
                "ground_velocity_source": relative["ground_velocity_source"],
            },
        ),
        story_stiffness_rows=shear_story_stiffness_table(model_config.stories),
    )


def run_euler_imposed_support_result(config: EulerBeamModelConfig | str | Path | dict[str, Any]) -> AnalysisResult:
    """Run an Euler beam case using true OpenSees imposed support motion."""

    ops = import_opensees()
    if isinstance(config, dict):
        model_config = normalize_euler_config(config)
        base_dir = Path(".")
    elif not isinstance(config, EulerBeamModelConfig):
        config_path = Path(config)
        model_config = load_euler_config(config_path)
        base_dir = config_path.parent
    else:
        model_config = config
        base_dir = Path(".")

    ground = load_ground_motion(model_config.ground_motion, base_dir)
    ground_full = ground_kinematics(ground["time"], ground["ax"], ground["ay"])
    structural_model = EulerBeam2DModel.from_config(model_config)
    mass = structural_model.mass_matrix()
    stiffness = structural_model.stiffness_matrix()
    alpha, beta = rayleigh_coefficients(mass, stiffness, model_config.damping)
    damping = alpha * mass + beta * stiffness
    response = _run_euler_imposed_support(
        ops,
        model_config,
        ground["time"],
        ground_full["displacement"][:, 0],
        ground_full["velocity"][:, 0],
        ground["ax"],
        alpha,
        beta,
    )
    relative_displacement = response["absolute_displacement"].copy()
    relative_velocity = response["absolute_velocity"].copy()
    relative_acceleration = response["absolute_acceleration"].copy()
    relative_displacement[:, :, 0] -= ground_full["displacement"][:, 0, None]
    relative_velocity[:, :, 0] -= ground_full["velocity"][:, 0, None]
    relative_acceleration[:, :, 0] -= ground["ax"][:, None]
    payload = {
        "time": response["time"],
        "displacement": relative_displacement,
        "velocity": relative_velocity,
        "acceleration": relative_acceleration,
        "absolute_displacement": response["absolute_displacement"],
        "absolute_velocity": response["absolute_velocity"],
        "absolute_acceleration": response["absolute_acceleration"],
        "ground_displacement": ground_full["displacement"],
        "ground_velocity": ground_full["velocity"],
        "ground_acceleration": ground_full["acceleration"],
        "ground_displacement_source": "integrated_from_acceleration",
        "ground_velocity_source": "integrated_from_acceleration",
    }
    return AnalysisResult(
        time=payload["time"],
        relative=ResponseHistory(
            displacement=payload["displacement"],
            velocity=payload["velocity"],
            acceleration=payload["acceleration"],
        ),
        absolute=ResponseHistory(
            displacement=payload["absolute_displacement"],
            velocity=payload["absolute_velocity"],
            acceleration=payload["absolute_acceleration"],
        ),
        ground=ResponseHistory(
            displacement=payload["ground_displacement"],
            velocity=payload["ground_velocity"],
            acceleration=payload["ground_acceleration"],
        ),
        sensors=build_beam_sensor_result(model_config.sensors, payload),
        mass_matrix=mass,
        stiffness_matrix=stiffness,
        damping_matrix=damping,
        modal=modal_analysis(mass, stiffness),
        metadata=AnalysisMetadata(
            backend="opensees_euler_imposed_support",
            response_definition=(
                "OpenSees MultipleSupport imposed support motion for Euler beam; "
                "node translations are converted to relative U by subtracting imposed base motion"
            ),
            rayleigh_alpha=alpha,
            rayleigh_beta=beta,
            extras=opensees_provenance() | {
                "model_type": model_config.model_type,
                "dof_per_floor": list(model_config.dof_per_floor),
                "response_source": "opensees_imposed_support_motion",
                "base_excitation_source": "OpenSees MultipleSupport imposedMotion",
                "ground_displacement_source": payload["ground_displacement_source"],
                "ground_velocity_source": payload["ground_velocity_source"],
            },
        ),
        story_stiffness_rows=_euler_section_rows(model_config),
    )


def _run_shear_imposed_support(
    ops: Any,
    config: ShearModelConfig,
    time: np.ndarray,
    ground_disp: np.ndarray,
    ground_vel: np.ndarray,
    ground_accel: np.ndarray,
    rayleigh_alpha: float,
    rayleigh_beta: float,
) -> dict[str, np.ndarray]:
    ops.wipe()
    ops.model("basic", "-ndm", 1, "-ndf", 1)

    base_tag = 1
    ops.node(base_tag, 0.0)
    ops.fix(base_tag, 1)

    node_tags = []
    for story in config.stories:
        tag = 1000 + story.story
        node_tags.append(tag)
        ops.node(tag, 0.0)
        ops.mass(tag, story.mass)

    for story in config.stories:
        mat_tag = story.story
        ele_tag = story.story
        lower = base_tag if story.story == 1 else 1000 + story.story - 1
        upper = 1000 + story.story
        ops.uniaxialMaterial("Elastic", mat_tag, story.stiffness)
        ops.element("zeroLength", ele_tag, lower, upper, "-mat", mat_tag, "-dir", 1, "-doRayleigh", 1)

    dt = float(time[1] - time[0])
    disp_tag = 11
    vel_tag = 12
    accel_tag = 13
    motion_tag = 21
    ops.timeSeries("Path", disp_tag, "-dt", dt, "-values", *ground_disp.tolist(), "-useLast")
    ops.timeSeries("Path", vel_tag, "-dt", dt, "-values", *ground_vel.tolist(), "-useLast")
    ops.timeSeries("Path", accel_tag, "-dt", dt, "-values", *ground_accel.tolist(), "-useLast")
    ops.pattern("MultipleSupport", 1)
    ops.groundMotion(motion_tag, "Plain", "-disp", disp_tag, "-vel", vel_tag, "-accel", accel_tag)
    ops.imposedMotion(base_tag, 1, motion_tag)

    ops.constraints("Transformation")
    ops.numberer("RCM")
    ops.system("BandGeneral")
    ops.test("NormDispIncr", 1.0e-10, 10)
    ops.algorithm("Linear")
    ops.integrator("Newmark", 0.5, 0.25)
    ops.rayleigh(rayleigh_alpha, rayleigh_beta, 0.0, 0.0)
    ops.analysis("Transient")

    n_steps = time.size
    n = config.num_stories
    abs_disp = np.zeros((n_steps, n), dtype=float)
    abs_vel = np.zeros_like(abs_disp)
    abs_acc = np.zeros_like(abs_disp)
    for step in range(n_steps):
        if step > 0:
            ok = ops.analyze(1, dt)
            if ok != 0:
                raise RuntimeError(f"OpenSees imposed-support analysis failed at step {step} with code {ok}.")
        for i, tag in enumerate(node_tags):
            abs_disp[step, i] = ops.nodeDisp(tag, 1)
            abs_vel[step, i] = ops.nodeVel(tag, 1)
            abs_acc[step, i] = ops.nodeAccel(tag, 1)
    return {
        "time": time,
        "absolute_displacement": abs_disp,
        "absolute_velocity": abs_vel,
        "absolute_acceleration": abs_acc,
    }


def _run_euler_imposed_support(
    ops: Any,
    config: EulerBeamModelConfig,
    time: np.ndarray,
    ground_disp: np.ndarray,
    ground_vel: np.ndarray,
    ground_accel: np.ndarray,
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
    for section in config.sections:
        ele_tag = section.story
        lower = base_tag if section.story == 1 else 1000 + section.story - 1
        upper = 1000 + section.story
        mass_per_length = section.density * section.A
        ops.element(
            "elasticBeamColumn",
            ele_tag,
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

    dt = float(time[1] - time[0])
    disp_tag = 11
    vel_tag = 12
    accel_tag = 13
    motion_tag = 21
    ops.timeSeries("Path", disp_tag, "-dt", dt, "-values", *ground_disp.tolist(), "-useLast")
    ops.timeSeries("Path", vel_tag, "-dt", dt, "-values", *ground_vel.tolist(), "-useLast")
    ops.timeSeries("Path", accel_tag, "-dt", dt, "-values", *ground_accel.tolist(), "-useLast")
    ops.pattern("MultipleSupport", 1)
    ops.groundMotion(motion_tag, "Plain", "-disp", disp_tag, "-vel", vel_tag, "-accel", accel_tag)
    ops.imposedMotion(base_tag, 1, motion_tag)

    ops.constraints("Transformation")
    ops.numberer("RCM")
    ops.system("BandGeneral")
    ops.test("NormDispIncr", 1.0e-10, 10)
    ops.algorithm("Linear")
    ops.integrator("Newmark", 0.5, 0.25)
    ops.rayleigh(rayleigh_alpha, rayleigh_beta, 0.0, 0.0)
    ops.analysis("Transient")

    n_steps = time.size
    n = config.num_stories
    abs_disp = np.zeros((n_steps, n, 2), dtype=float)
    abs_vel = np.zeros_like(abs_disp)
    abs_acc = np.zeros_like(abs_disp)
    for step in range(n_steps):
        if step > 0:
            ok = ops.analyze(1, dt)
            if ok != 0:
                raise RuntimeError(f"OpenSees Euler imposed-support analysis failed at step {step} with code {ok}.")
        for story_index, tag in enumerate(node_tags):
            abs_disp[step, story_index, 0] = ops.nodeDisp(tag, 1)
            abs_disp[step, story_index, 1] = -ops.nodeDisp(tag, 3)
            abs_vel[step, story_index, 0] = ops.nodeVel(tag, 1)
            abs_vel[step, story_index, 1] = -ops.nodeVel(tag, 3)
            abs_acc[step, story_index, 0] = ops.nodeAccel(tag, 1)
            abs_acc[step, story_index, 1] = -ops.nodeAccel(tag, 3)
    return {
        "time": time,
        "absolute_displacement": abs_disp,
        "absolute_velocity": abs_vel,
        "absolute_acceleration": abs_acc,
    }


def _euler_section_rows(config: EulerBeamModelConfig) -> list[dict[str, Any]]:
    return [
        {
            "story": section.story,
            "height": config.geometry.story_heights[section.story - 1],
            "E": section.E,
            "A": section.A,
            "I": section.I,
            "density": section.density,
        }
        for section in config.sections
    ]


__all__ = ["run_euler_imposed_support_result", "run_shear_imposed_support_result"]
