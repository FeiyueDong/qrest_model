"""OpenSeesPy import helpers."""

from __future__ import annotations

from typing import Any


def import_opensees() -> Any:
    try:
        import openseespy.opensees as ops  # type: ignore[import-not-found]

        return ops
    except ImportError as openseespy_error:
        try:
            import openseespylinux.opensees as ops  # type: ignore[import-not-found]

            return ops
        except ImportError as linux_error:
            raise RuntimeError(
                "OpenSees backend requires openseespy or openseespylinux to be installed."
            ) from linux_error
