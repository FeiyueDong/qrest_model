"""Research dataset exporter with explicit truth/observation separation."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from qrest_model.analysis.result import AnalysisResult, ObservationChannel
from qrest_model.common.io import ensure_output_dir
from qrest_model.exporters.derived_quantities import write_derived_quantities
from qrest_model.exporters.model_truth import write_model_truth


def write_research_dataset(
    output_dir: str | Path,
    *,
    name: str,
    config: dict[str, Any],
    result: AnalysisResult,
    backend: str = "direct",
    truth_policy: dict[str, Any] | None = None,
    observation_config: dict[str, Any] | None = None,
    noise_config: dict[str, Any] | None = None,
    export_policy: dict[str, Any] | None = None,
    research: dict[str, Any] | None = None,
) -> Path:
    output = ensure_output_dir(output_dir)
    (output / "config.json").write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    truth_summary = write_model_truth(output / "truth", result, config)
    derived_metadata = write_derived_quantities(output / "derived", result, config)
    observation_files = write_observation_tables(output / "observations", result)
    observation_metadata = build_observation_metadata(result, observation_files)
    metadata_dir = ensure_output_dir(output / "metadata")
    (metadata_dir / "observation.json").write_text(
        json.dumps(observation_metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (metadata_dir / "derived.json").write_text(
        json.dumps(derived_metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    provenance = build_research_provenance(
        name=name,
        config=config,
        result=result,
        backend=backend,
        truth_policy=truth_policy,
        observation_config=observation_config,
        noise_config=noise_config,
        export_policy=export_policy,
        research=research,
    )
    (metadata_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "name": name,
        "dataset_type": "research",
        "schema_version": "1.0",
        "model_type": truth_summary["model_type"],
        "backend": backend,
        "deterministic": True,
        "config_hash_sha256": provenance["config_hash_sha256"],
        "truth_policy": truth_policy or {},
        "observation_config": observation_config or {},
        "noise_config": noise_config or {},
        "export_policy": export_policy or {},
        "research": research or {},
        "truth": {"directory": "truth", **truth_summary["files"]},
        "derived": {"directory": "derived", **derived_metadata["files"]},
        "observations": observation_files,
        "content_summary": build_content_summary(
            truth_summary,
            observation_metadata,
            derived_metadata,
        ),
        "metadata": {
            "derived": "metadata/derived.json",
            "observation": "metadata/observation.json",
            "provenance": "metadata/provenance.json",
        },
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return output


def write_observation_tables(output_dir: str | Path, result: AnalysisResult) -> dict[str, dict[str, str]]:
    output = ensure_output_dir(output_dir)
    ensure_output_dir(output / "physical")
    ensure_output_dir(output / "virtual")
    observations = result.observations
    if observations is None or not observations.channels:
        return {"physical": {}, "virtual": {}}

    files: dict[str, dict[str, str]] = {"physical": {}, "virtual": {}}
    for kind in ("physical", "virtual"):
        channel_indices = [
            (index, channel)
            for index, channel in enumerate(observations.channels)
            if channel.kind == kind
        ]
        for quantity in ("displacement", "velocity", "acceleration"):
            histories = _quantity_histories(observations, quantity, kind=kind)
            selected = [
                (channel, histories[index])
                for index, channel in channel_indices
                if histories is not None and _canonical_quantity(channel.quantity) == quantity
            ]
            if not selected:
                continue
            relative_path = Path(kind) / f"{quantity}.csv"
            _write_wide_observation_csv(output / relative_path, result.time, selected)
            files[kind][quantity] = str(relative_path)
    return files


def build_observation_metadata(result: AnalysisResult, files: dict[str, dict[str, str]]) -> dict[str, Any]:
    observations = result.observations
    channels = [] if observations is None else [channel.to_dict() for channel in observations.channels]
    physical = [channel for channel in channels if channel["kind"] == "physical"]
    virtual = [channel for channel in channels if channel["kind"] == "virtual"]
    return {
        "channel_count": len(channels),
        "physical_channel_count": len(physical),
        "virtual_channel_count": len(virtual),
        "channels": channels,
        "files": files,
    }


def build_content_summary(
    truth_summary: dict[str, Any],
    observation_metadata: dict[str, Any],
    derived_metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "time_steps": int(truth_summary["time_steps"]),
        "dof_count": int(truth_summary["dof_count"]),
        "physical_channel_count": int(observation_metadata["physical_channel_count"]),
        "virtual_channel_count": int(observation_metadata["virtual_channel_count"]),
        "observation_quantities": sorted(
            {
                _canonical_quantity(str(channel["quantity"]))
                for channel in observation_metadata.get("channels", [])
            }
        ),
        "derived_quantity_ids": [
            str(quantity["id"])
            for quantity in derived_metadata.get("quantities", [])
        ],
    }


def build_research_provenance(
    *,
    name: str,
    config: dict[str, Any],
    result: AnalysisResult,
    backend: str,
    truth_policy: dict[str, Any] | None = None,
    observation_config: dict[str, Any] | None = None,
    noise_config: dict[str, Any] | None = None,
    export_policy: dict[str, Any] | None = None,
    research: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = result.metadata.to_dict()
    return {
        "name": name,
        "backend": backend,
        "analysis_backend": result.metadata.backend,
        "model_type": str(config.get("model", {}).get("type", metadata.get("model_type", ""))),
        "config_hash_sha256": stable_config_hash(config),
        "random_seed": None,
        "deterministic": True,
        "truth_policy": truth_policy or {},
        "observation_config": observation_config or {},
        "noise_config": noise_config or {},
        "export_policy": export_policy or {},
        "research": research or {},
        "analysis_metadata": metadata,
    }


def stable_config_hash(config: dict[str, Any]) -> str:
    payload = json.dumps(config, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _quantity_histories(observations, quantity: str, *, kind: str):
    if kind == "physical":
        absolute_name = f"absolute_{quantity}"
        absolute = getattr(observations, absolute_name)
        if absolute is not None:
            return absolute
    return getattr(observations, quantity)


def _write_wide_observation_csv(
    path: Path,
    time: np.ndarray,
    selected: list[tuple[ObservationChannel, np.ndarray]],
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = ["time"] + [channel.observation_id for channel, _history in selected]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for step, t in enumerate(time):
            row: dict[str, Any] = {"time": float(t)}
            for channel, history in selected:
                row[channel.observation_id] = _channel_value(channel, history, step)
            writer.writerow(row)


def _canonical_quantity(quantity: str) -> str:
    normalized = quantity.lower()
    if normalized in {"disp", "displacement"}:
        return "displacement"
    if normalized in {"vel", "velocity"}:
        return "velocity"
    if normalized in {"accel", "acceleration"}:
        return "acceleration"
    raise ValueError(f"Unsupported observation quantity: {quantity}")


def _channel_value(channel: ObservationChannel, history: np.ndarray, step: int) -> float:
    value = np.asarray(history[step], dtype=float)
    if value.ndim == 0:
        return float(value)
    if value.ndim != 1:
        raise ValueError(f"Observation history for {channel.observation_id} must be scalar or one-dimensional per step.")
    return float(value[_component_index(channel, int(value.size))])


def _component_index(channel: ObservationChannel, component_count: int) -> int:
    label = (channel.direction or channel.dof or "").upper()
    if label in {"X", "UX", "U"}:
        return 0
    if label in {"Y", "UY"}:
        if component_count < 2:
            raise ValueError(f"Observation {channel.observation_id} has no Y component.")
        return 1
    if label == "THETA":
        if component_count < 2:
            raise ValueError(f"Observation {channel.observation_id} has no Theta component.")
        return 1
    if label == "RZ":
        if component_count < 3:
            raise ValueError(f"Observation {channel.observation_id} has no RZ component.")
        return 2
    raise ValueError(f"Observation {channel.observation_id} does not define a component label.")


__all__ = [
    "build_observation_metadata",
    "build_research_provenance",
    "stable_config_hash",
    "write_observation_tables",
    "write_research_dataset",
]
