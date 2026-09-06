"""Metadata helpers for analysis result provenance."""

from __future__ import annotations

from typing import Any


def direct_provenance() -> dict[str, Any]:
    return {
        "matrix_source": "qrest_model_theory",
        "modal_source": "qrest_model_matrix",
        "response_source": "direct_newmark",
    }


def opensees_provenance() -> dict[str, Any]:
    return {
        "matrix_source": "qrest_model_theory",
        "modal_source": "qrest_model_matrix",
        "backend_modal_source": "opensees_eigen",
        "response_source": "opensees",
    }


__all__ = ["direct_provenance", "opensees_provenance"]
