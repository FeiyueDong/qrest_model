"""Matrix assembly for one-direction shear-building models."""

from __future__ import annotations

import numpy as np

from qrest_model.schema import ShearStoryConfig


def assemble_shear_mass(stories: tuple[ShearStoryConfig, ...]) -> np.ndarray:
    return np.diag([story.mass for story in stories]).astype(float)


def assemble_shear_stiffness(stories: tuple[ShearStoryConfig, ...]) -> np.ndarray:
    n = len(stories)
    stiffness = np.zeros((n, n), dtype=float)
    for i, story in enumerate(stories):
        k = story.stiffness
        stiffness[i, i] += k
        if i > 0:
            stiffness[i - 1, i - 1] += k
            stiffness[i, i - 1] -= k
            stiffness[i - 1, i] -= k
    return stiffness


def shear_story_stiffness_table(stories: tuple[ShearStoryConfig, ...]) -> list[dict[str, float]]:
    return [{"story": story.story, "stiffness": story.stiffness} for story in stories]

