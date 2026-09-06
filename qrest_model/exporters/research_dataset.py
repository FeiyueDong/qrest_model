"""Research dataset exporter with explicit truth/observation separation."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from qrest_model.analysis.result import AnalysisResult, ObservationChannel, ObservationResult
from qrest_model.common.io import ensure_output_dir
from qrest_model.exporters.derived_quantities import write_derived_quantities
from qrest_model.exporters.model_truth import write_model_truth
from qrest_model.noise import apply_observation_noise, normalize_noise_config
from qrest_model.observations.series import (
    canonical_quantity,
    extract_channel_series,
    observation_histories,
)


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
    normalized_noise = normalize_noise_config(noise_config)
    if normalized_noise.enabled:
        if result.observations is None:
            raise ValueError("Noise requires observations.")
        clean_files = write_observation_tables(
            output / "observations",
            result,
            outputs=(("physical", "physical_clean"), ("virtual", "virtual")),
        )
        noisy_observations, noise_metadata = apply_observation_noise(result.observations, normalized_noise)
        noisy_files = write_observation_tables(
            output / "observations",
            result,
            observations=noisy_observations,
            outputs=(("physical", "physical"),),
        )
        observation_files = {
            "physical": noisy_files["physical"],
            "physical_clean": clean_files["physical_clean"],
            "virtual": clean_files["virtual"],
        }
        observation_metadata = build_observation_metadata(noisy_observations, observation_files)
    else:
        observation_files = write_observation_tables(output / "observations", result)
        observation_metadata = build_observation_metadata(result.observations, observation_files)
        noise_metadata = normalized_noise.to_dict() | {"channels": []}
    metadata_dir = ensure_output_dir(output / "metadata")
    (metadata_dir / "observation.json").write_text(
        json.dumps(observation_metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (metadata_dir / "derived.json").write_text(
        json.dumps(derived_metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (metadata_dir / "noise.json").write_text(
        json.dumps(noise_metadata, indent=2, ensure_ascii=False) + "\n",
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
        "excitation": provenance["excitation"],
        "config_hash_sha256": provenance["config_hash_sha256"],
        "model_config_hash_sha256": provenance["model_config_hash_sha256"],
        "dataset_config_hash_sha256": provenance["dataset_config_hash_sha256"],
        "truth_policy": truth_policy or {},
        "observation_config": observation_config or {},
        "noise_config": noise_config or {},
        "noise": {
            "configured": normalized_noise.enabled,
            "seed": normalized_noise.seed,
            "type": normalized_noise.noise_type if normalized_noise.enabled else "none",
            "target": normalized_noise.target,
            "level": {
                "mode": normalized_noise.level_mode,
                "value": normalized_noise.level_value,
            },
        },
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
            "noise": "metadata/noise.json",
            "observation": "metadata/observation.json",
            "provenance": "metadata/provenance.json",
        },
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return output


def write_observation_tables(
    output_dir: str | Path,
    result: AnalysisResult,
    *,
    observations: ObservationResult | None = None,
    outputs: tuple[tuple[str, str], ...] = (("physical", "physical"), ("virtual", "virtual")),
) -> dict[str, dict[str, str]]:
    output = ensure_output_dir(output_dir)
    for _kind, output_kind in outputs:
        ensure_output_dir(output / output_kind)
    observations = result.observations if observations is None else observations
    if observations is None or not observations.channels:
        return {output_kind: {} for _kind, output_kind in outputs}

    files: dict[str, dict[str, str]] = {output_kind: {} for _kind, output_kind in outputs}
    for kind, output_kind in outputs:
        channel_indices = [
            (index, channel)
            for index, channel in enumerate(observations.channels)
            if channel.kind == kind
        ]
        for quantity in ("displacement", "velocity", "acceleration"):
            histories = observation_histories(observations, quantity, kind=kind, absolute=(kind == "physical"))
            selected = [
                (channel, extract_channel_series(channel, histories[index]))
                for index, channel in channel_indices
                if histories is not None and canonical_quantity(channel.quantity) == quantity
            ]
            if not selected:
                continue
            relative_path = Path(output_kind) / f"{quantity}.csv"
            _write_wide_observation_csv(output / relative_path, result.time, selected)
            files[output_kind][quantity] = str(relative_path)
    return files


def build_observation_metadata(observations: ObservationResult | None, files: dict[str, dict[str, str]]) -> dict[str, Any]:
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
    excitation = build_excitation_metadata(config)
    return {
        "name": name,
        "backend": backend,
        "analysis_backend": result.metadata.backend,
        "model_type": str(config.get("model", {}).get("type", metadata.get("model_type", ""))),
        "config_hash_sha256": stable_config_hash(config),
        "model_config_hash_sha256": stable_config_hash(config),
        "dataset_config_hash_sha256": stable_dataset_config_hash(
            config=config,
            truth_policy=truth_policy,
            observation_config=observation_config,
            noise_config=noise_config,
            export_policy=export_policy,
            research=research,
        ),
        "random_seed": excitation.get("seed"),
        "deterministic": True,
        "excitation": excitation,
        "truth_policy": truth_policy or {},
        "observation_config": observation_config or {},
        "noise_config": noise_config or {},
        "export_policy": export_policy or {},
        "research": research or {},
        "analysis_metadata": metadata,
    }


def stable_config_hash(config: dict[str, Any]) -> str:
    return stable_json_hash(structural_model_config(config))


def stable_dataset_config_hash(
    *,
    config: dict[str, Any],
    truth_policy: dict[str, Any] | None = None,
    observation_config: dict[str, Any] | None = None,
    noise_config: dict[str, Any] | None = None,
    export_policy: dict[str, Any] | None = None,
    research: dict[str, Any] | None = None,
) -> str:
    return stable_json_hash(
        {
            "model_config": structural_model_config(config),
            "truth_policy": truth_policy or {},
            "observation_config": observation_config or {},
            "noise_config": noise_config or {},
            "export_policy": export_policy or {},
            "research": research or {},
        }
    )


def structural_model_config(config: dict[str, Any]) -> dict[str, Any]:
    structural = json.loads(json.dumps(config, ensure_ascii=False))
    structural.pop("sensors", None)
    return structural


def build_excitation_metadata(config: dict[str, Any]) -> dict[str, Any]:
    ground_motion = dict(config.get("ground_motion", {}))
    motion_type = str(ground_motion.get("type", "")).lower()
    if not motion_type:
        motion_type = "recorded" if ground_motion.get("ax_file") or ground_motion.get("ay_file") else "synthetic"
    stochastic = dict(ground_motion.get("stochastic", {}))
    if motion_type == "stochastic" and not stochastic:
        stochastic = {
            key: value
            for key, value in ground_motion.items()
            if key not in {"type", "dt", "duration", "ax_file", "ay_file", "ax_scale", "ay_scale", "synthetic"}
        }
    return {
        "type": motion_type,
        "dt": float(ground_motion.get("dt", 0.0)),
        "duration": float(ground_motion.get("duration", 0.0)),
        "seed": stochastic.get("seed") if motion_type == "stochastic" else None,
        "source": _excitation_source(ground_motion, motion_type),
    }


def _excitation_source(ground_motion: dict[str, Any], motion_type: str) -> str:
    if ground_motion.get("ax_file") or ground_motion.get("ay_file"):
        return "file"
    if motion_type == "stochastic":
        return "generated_stochastic"
    return "generated_synthetic"


def stable_json_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


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
            for channel, series in selected:
                row[channel.observation_id] = float(series[step])
            writer.writerow(row)


def _canonical_quantity(quantity: str) -> str:
    return canonical_quantity(quantity)


__all__ = [
    "build_observation_metadata",
    "build_excitation_metadata",
    "build_research_provenance",
    "stable_config_hash",
    "write_observation_tables",
    "write_research_dataset",
]
