"""Compatibility imports for the qREST model schema.

New code should import from :mod:`qrest_model.schema`.
"""

from qrest_model.schema.case import *  # noqa: F403
from qrest_model.schema.case import (
    __all__,
    _finite_float,
    _normalize_element,
    _normalize_model_type,
    _normalize_rigid_story,
    _normalize_schema_version,
    _normalize_sensor,
    _point,
    _to_centroid,
    _validate_story_ids,
    _validate_unique_sensor_ids,
)

_normalize_story = _normalize_rigid_story
