"""Optional OpenSeesPy backend for three-DOF rigid-floor story models."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from qrest_model.analysis.result import AnalysisMetadata, AnalysisResult, ResponseHistory, SensorResult
from qrest_model.schema import ElementConfig, ModelConfig, StoryConfig, load_config
from qrest_model.common.damping import rayleigh_coefficients
from qrest_model.common.ground_motion import load_ground_motion
from qrest_model.common.opensees import import_opensees
from qrest_model.common.response import add_absolute_floor_response
from qrest_model.exporters.backend_outputs import write_story3d_outputs
from qrest_model.models.rigid_floor import RigidFloorBuildingModel
from qrest_model.postprocess.sensor_mapping import build_sensor_rows_from_motion
from qrest_model.theory.story_stiffness import story_stiffness_table


def run(config: ModelConfig | str | Path, output_dir: str | Path | None = None) -> dict[str, Any]:
    result = run_result(config)
    legacy = result.to_legacy_dict()
    legacy["stiffness_matrix_theory"] = legacy["stiffness_matrix"]
    if output_dir is not None:
        write_outputs(legacy, output_dir)
    return legacy


def run_result(config: ModelConfig | str | Path) -> AnalysisResult:
    ops = import_opensees()
    if not isinstance(config, ModelConfig):
        config_path = Path(config)
        model_config = load_config(config_path)
        base_dir = config_path.parent
    else:
        model_config = config
        base_dir = Path(".")
    _validate_opensees_element_connectivity(model_config)

    ground = load_ground_motion(model_config.ground_motion, base_dir)
    structural_model = RigidFloorBuildingModel.from_config(model_config)
    mass_matrix = structural_model.mass_matrix()
    stiffness_matrix = structural_model.stiffness_matrix()
    alpha, beta = rayleigh_coefficients(mass_matrix, stiffness_matrix, model_config.damping)
    response = _run_opensees(ops, model_config, ground, alpha, beta)
    sensor_rows = build_sensor_rows_from_motion(
        model_config.sensors,
        response["time"],
        response["sensor_displacement"],
        response["sensor_velocity"],
        response["sensor_acceleration"],
        response["sensor_absolute_displacement"],
        response["sensor_absolute_velocity"],
        response["sensor_absolute_acceleration"],
    )
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
        sensors=SensorResult(
            rows=sensor_rows,
            displacement=response["sensor_displacement"],
            velocity=response["sensor_velocity"],
            acceleration=response["sensor_acceleration"],
            absolute_displacement=response["sensor_absolute_displacement"],
            absolute_velocity=response["sensor_absolute_velocity"],
            absolute_acceleration=response["sensor_absolute_acceleration"],
        ),
        mass_matrix=mass_matrix,
        stiffness_matrix=stiffness_matrix,
        damping_matrix=alpha * mass_matrix + beta * stiffness_matrix,
        metadata=AnalysisMetadata(
            backend="opensees_story",
            response_definition=(
                "OpenSees UniformExcitation node response is treated as relative response; "
                "abs_* columns include ground translation from integrated input acceleration"
            ),
            rayleigh_alpha=alpha,
            rayleigh_beta=beta,
            extras={
                "ground_displacement_source": response["ground_displacement_source"],
                "ground_velocity_source": response["ground_velocity_source"],
            },
        ),
        story_stiffness_rows=story_stiffness_table(model_config.stories),
    )


def _run_opensees(
    ops: Any,
    config: ModelConfig,
    ground: dict[str, np.ndarray],
    rayleigh_alpha: float,
    rayleigh_beta: float,
) -> dict[str, Any]:
    ops.wipe()
    ops.model("basic", "-ndm", 2, "-ndf", 3)

    master_tags = {0: 1}
    sensor_tags: dict[str, int] = {}
    ops.node(1, 0.0, 0.0)
    ops.fix(1, 1, 1, 1)

    next_node = 10
    use_element_ids = _use_element_ids(config.stories)
    spring_nodes: dict[tuple[int, str], int] = {}
    for story in config.stories:
        master = 1000 + story.story
        master_tags[story.story] = master
        ops.node(master, 0.0, 0.0)
        ops.mass(master, story.mass, story.mass, story.jz)
        for element_index, element in enumerate(story.elements):
            element_key = _element_key(element_index, element, use_element_ids)
            node = next_node
            next_node += 1
            ops.node(node, element.x, element.y)
            ops.rigidLink("beam", master, node)
            spring_nodes[(story.story, element_key)] = node
        for sensor in config.sensors:
            if sensor.story != story.story:
                continue
            node = next_node
            next_node += 1
            ops.node(node, sensor.x, sensor.y)
            ops.rigidLink("beam", master, node)
            sensor_tags[sensor.sensor_id] = node

    ground_nodes: dict[str, int] = {}
    if config.stories and config.stories[0].elements:
        for element_index, element in enumerate(config.stories[0].elements):
            element_key = _element_key(element_index, element, use_element_ids)
            node = next_node
            next_node += 1
            ops.node(node, element.x, element.y)
            ops.fix(node, 1, 1, 1)
            ground_nodes[element_key] = node

    next_mat = 1
    next_ele = 1
    for story in config.stories:
        for element_index, element in enumerate(story.elements):
            element_key = _element_key(element_index, element, use_element_ids)
            lower = ground_nodes[element_key] if story.story == 1 else spring_nodes[(story.story - 1, element_key)]
            upper = spring_nodes[(story.story, element_key)]
            mat_x = next_mat
            mat_y = next_mat + 1
            next_mat += 2
            ops.uniaxialMaterial("Elastic", mat_x, element.kx)
            ops.uniaxialMaterial("Elastic", mat_y, element.ky)
            ops.element("zeroLength", next_ele, lower, upper, "-mat", mat_x, mat_y, "-dir", 1, 2, "-doRayleigh", 1)
            next_ele += 1

    dt = float(ground["time"][1] - ground["time"][0])
    ops.timeSeries("Path", 1, "-dt", dt, "-values", *ground["ax"].tolist(), "-useLast")
    ops.pattern("UniformExcitation", 1, 1, "-accel", 1)
    ops.timeSeries("Path", 2, "-dt", dt, "-values", *ground["ay"].tolist(), "-useLast")
    ops.pattern("UniformExcitation", 2, 2, "-accel", 2)
    ops.constraints("Transformation")
    ops.numberer("RCM")
    ops.system("BandGeneral")
    ops.test("NormDispIncr", 1.0e-10, 10)
    ops.algorithm("Linear")
    ops.integrator("Newmark", 0.5, 0.25)
    ops.rayleigh(rayleigh_alpha, rayleigh_beta, 0.0, 0.0)
    ops.analysis("Transient")
    initial_accel = (-float(ground["ax"][0]), -float(ground["ay"][0]), 0.0)
    for tag in list(master_tags.values())[1:]:
        _set_node_accel(ops, tag, initial_accel)
    for tag in spring_nodes.values():
        _set_node_accel(ops, tag, initial_accel)
    for tag in sensor_tags.values():
        _set_node_accel(ops, tag, initial_accel)

    n_steps = ground["time"].size
    disp = np.zeros((n_steps, config.num_stories, 3), dtype=float)
    vel = np.zeros_like(disp)
    acc = np.zeros_like(disp)
    sensor_count = len(config.sensors)
    sensor_disp = np.zeros((sensor_count, n_steps, 3), dtype=float)
    sensor_vel = np.zeros_like(sensor_disp)
    sensor_acc = np.zeros_like(sensor_disp)
    for step in range(n_steps):
        if step > 0:
            ok = ops.analyze(1, dt)
            if ok != 0:
                raise RuntimeError(f"OpenSees analysis failed at step {step} with code {ok}.")
        for i in range(config.num_stories):
            tag = master_tags[i + 1]
            disp[step, i, :] = ops.nodeDisp(tag)
            vel[step, i, :] = ops.nodeVel(tag)
            acc[step, i, :] = ops.nodeAccel(tag)
        for sensor_index, sensor in enumerate(config.sensors):
            tag = sensor_tags[sensor.sensor_id]
            sensor_disp[sensor_index, step, :] = ops.nodeDisp(tag)
            sensor_vel[sensor_index, step, :] = ops.nodeVel(tag)
            sensor_acc[sensor_index, step, :] = ops.nodeAccel(tag)

    ground_acc = np.column_stack([ground["ax"], ground["ay"]])
    response = {"time": ground["time"], "displacement": disp, "velocity": vel, "acceleration": acc}
    add_absolute_floor_response(response, ground["ax"], ground["ay"])
    ground_disp = response["ground_displacement"]
    ground_vel = response["ground_velocity"]
    sensor_abs_disp = sensor_disp.copy()
    sensor_abs_vel = sensor_vel.copy()
    sensor_abs_acc = sensor_acc.copy()
    sensor_abs_disp[:, :, 0] += ground_disp[:, 0]
    sensor_abs_disp[:, :, 1] += ground_disp[:, 1]
    sensor_abs_vel[:, :, 0] += ground_vel[:, 0]
    sensor_abs_vel[:, :, 1] += ground_vel[:, 1]
    sensor_abs_acc[:, :, 0] += ground_acc[:, 0]
    sensor_abs_acc[:, :, 1] += ground_acc[:, 1]
    response.update(
        {
            "sensor_displacement": tuple(sensor_disp),
            "sensor_velocity": tuple(sensor_vel),
            "sensor_acceleration": tuple(sensor_acc),
            "sensor_absolute_displacement": tuple(sensor_abs_disp),
            "sensor_absolute_velocity": tuple(sensor_abs_vel),
            "sensor_absolute_acceleration": tuple(sensor_abs_acc),
        }
    )
    return response


def _set_node_accel(ops: Any, node_tag: int, values: tuple[float, float, float]) -> None:
    for dof, value in enumerate(values, start=1):
        ops.setNodeAccel(node_tag, dof, value, "-commit")


def _validate_opensees_element_connectivity(config: ModelConfig, tolerance: float = 1.0e-9) -> None:
    if any(not story.elements for story in config.stories):
        raise ValueError(
            "OpenSees backend requires explicit story elements; direct_stiffness-only stories use the direct backend."
        )

    use_ids = _use_element_ids(config.stories)
    if use_ids:
        expected_ids = _story_element_ids(config.stories[0])
        for story in config.stories:
            story_ids = _story_element_ids(story)
            if len(story_ids) != len(set(story_ids)):
                raise ValueError(f"Story {story.story} defines duplicate element IDs.")
            if set(story_ids) != set(expected_ids):
                raise ValueError(
                    "OpenSees backend requires each story to define the same element ID set."
                )
    else:
        element_count = len(config.stories[0].elements)
        if any(len(story.elements) != element_count for story in config.stories):
            raise ValueError(
                "OpenSees backend requires each story to define the same number of elements when element IDs are omitted."
            )

    for lower_story, upper_story in zip(config.stories[:-1], config.stories[1:]):
        lower_elements = _elements_by_key(lower_story, use_ids)
        upper_elements = _elements_by_key(upper_story, use_ids)
        for key, lower_element in lower_elements.items():
            upper_element = upper_elements[key]
            if not np.allclose(
                [lower_element.x, lower_element.y],
                [upper_element.x, upper_element.y],
                rtol=0.0,
                atol=tolerance,
            ):
                raise ValueError(
                    "OpenSees zeroLength elements require matching x/y coordinates "
                    f"between stories {lower_story.story} and {upper_story.story} for element {key}."
                )


def _use_element_ids(stories: tuple[StoryConfig, ...]) -> bool:
    has_ids = [element.element_id is not None for story in stories for element in story.elements]
    if any(has_ids) and not all(has_ids):
        raise ValueError("OpenSees element IDs must be provided for every story element or omitted entirely.")
    return any(has_ids)


def _story_element_ids(story: StoryConfig) -> list[str]:
    ids: list[str] = []
    for element in story.elements:
        if element.element_id is None:
            raise ValueError(f"Story {story.story} has an element without an ID.")
        ids.append(element.element_id)
    return ids


def _elements_by_key(story: StoryConfig, use_element_ids: bool) -> dict[str, ElementConfig]:
    return {
        _element_key(index, element, use_element_ids): element
        for index, element in enumerate(story.elements)
    }


def _element_key(index: int, element: ElementConfig, use_element_ids: bool) -> str:
    if use_element_ids:
        if element.element_id is None:
            raise ValueError("Missing element ID.")
        return element.element_id
    return str(index)


def write_outputs(result: dict[str, Any], output_dir: str | Path) -> None:
    write_story3d_outputs(result, output_dir, stiffness_key="stiffness_matrix_theory")
