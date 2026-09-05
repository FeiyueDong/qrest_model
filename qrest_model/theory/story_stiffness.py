"""Story stiffness theory for rigid-floor three-DOF shear models."""

from __future__ import annotations

import numpy as np

from qrest_model.common.config import StoryConfig


def story_stiffness_from_elements(story: StoryConfig) -> np.ndarray:
    stiffness = np.zeros((3, 3), dtype=float)
    for element in story.elements:
        transform = np.array([[1.0, 0.0, -element.y], [0.0, 1.0, element.x]])
        local = np.diag([element.kx, element.ky])
        stiffness += transform.T @ local @ transform
    return stiffness


def story_stiffness_from_direct(story: StoryConfig) -> np.ndarray:
    if story.direct_stiffness is None:
        raise ValueError(f"Story {story.story} has no direct_stiffness config.")
    direct = story.direct_stiffness
    ex, ey = direct.stiffness_center
    return np.array(
        [
            [direct.kx, 0.0, -direct.kx * ey],
            [0.0, direct.ky, direct.ky * ex],
            [
                -direct.kx * ey,
                direct.ky * ex,
                direct.ktheta + direct.kx * ey * ey + direct.ky * ex * ex,
            ],
        ],
        dtype=float,
    )


def story_stiffness(story: StoryConfig) -> np.ndarray:
    if story.elements:
        return story_stiffness_from_elements(story)
    return story_stiffness_from_direct(story)


def story_stiffness_table(stories: tuple[StoryConfig, ...]) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    for story in stories:
        k = story_stiffness(story)
        rows.append(
            {
                "story": story.story,
                "k11": k[0, 0],
                "k12": k[0, 1],
                "k13": k[0, 2],
                "k21": k[1, 0],
                "k22": k[1, 1],
                "k23": k[1, 2],
                "k31": k[2, 0],
                "k32": k[2, 1],
                "k33": k[2, 2],
            }
        )
    return rows


def assemble_global_stiffness(stories: tuple[StoryConfig, ...]) -> np.ndarray:
    n = len(stories)
    total = np.zeros((3 * n, 3 * n), dtype=float)
    for i, story in enumerate(stories):
        block = story_stiffness(story)
        upper = slice(3 * i, 3 * i + 3)
        total[upper, upper] += block
        if i > 0:
            lower = slice(3 * (i - 1), 3 * (i - 1) + 3)
            total[lower, lower] += block
            total[upper, lower] -= block
            total[lower, upper] -= block
    return total


def assemble_mass(stories: tuple[StoryConfig, ...]) -> np.ndarray:
    mass = np.zeros((3 * len(stories), 3 * len(stories)), dtype=float)
    for i, story in enumerate(stories):
        idx = slice(3 * i, 3 * i + 3)
        mass[idx, idx] = np.diag([story.mass, story.mass, story.jz])
    return mass

