"""Research dataset generation workflow."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Iterable

from qrest_model.backends import run_analysis
from qrest_model.common.io import ensure_output_dir
from qrest_model.datasets.cases import RESEARCH_CONFIG_ROOT, DatasetCase, load_dataset_case, research_cases
from qrest_model.datasets.observations import apply_observation_config
from qrest_model.exporters.research_dataset import write_research_dataset


def generate_research_dataset(
    case: str | Path | dict[str, Any] | DatasetCase,
    output_dir: str | Path,
    *,
    name: str | None = None,
    backend: str = "direct",
) -> Path:
    dataset_name, config, metadata = _load_case_payload(case, name)
    runtime_config = apply_observation_config(config, metadata["observation_config"])
    output = reset_output_dir(output_dir)
    result = run_analysis(runtime_config, backend=backend)
    return write_research_dataset(
        output,
        name=dataset_name,
        config=runtime_config,
        result=result,
        backend=backend,
        truth_policy=metadata["truth_policy"],
        observation_config=metadata["observation_config"],
        noise_config=metadata["noise_config"],
        export_policy=metadata["export_policy"],
        research=metadata["research"],
    )


def generate_research_cases(
    output_root: str | Path,
    selected_names: Iterable[str] | None = None,
    config_root: str | Path = RESEARCH_CONFIG_ROOT,
    *,
    backend: str = "direct",
) -> list[Path]:
    selected = set(selected_names or [])
    cases = research_cases(config_root)
    available = {case.name for case in cases}
    unknown = selected - available
    if unknown:
        raise ValueError(
            f"Unknown research dataset case(s): {', '.join(sorted(unknown))}. "
            f"Available cases: {', '.join(sorted(available))}"
        )
    output_base = ensure_output_dir(output_root) if selected else reset_output_dir(output_root)
    generated: list[Path] = []
    for case in cases:
        if selected and case.name not in selected:
            continue
        generated.append(generate_research_dataset(case, output_base / case.name, backend=backend))
    write_research_dataset_index(output_base, generated)
    return generated


def write_research_dataset_index(output_root: str | Path, dataset_paths: Iterable[str | Path]) -> Path:
    output = ensure_output_dir(output_root)
    index = build_research_dataset_index(output, dataset_paths)
    path = output / "manifest.json"
    path.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def build_research_dataset_index(output_root: str | Path, dataset_paths: Iterable[str | Path]) -> dict[str, Any]:
    root = Path(output_root)
    datasets = [_dataset_index_entry(root, Path(path)) for path in dataset_paths]
    datasets.sort(key=lambda item: item["name"])
    return {
        "index_type": "research_dataset_collection",
        "schema_version": "1.0",
        "deterministic": True,
        "dataset_count": len(datasets),
        "datasets": datasets,
    }


def reset_output_dir(path: str | Path) -> Path:
    output = Path(path)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    return output


def _load_case_payload(
    case: str | Path | dict[str, Any] | DatasetCase,
    explicit_name: str | None,
) -> tuple[str, dict[str, Any], dict[str, dict[str, Any]]]:
    metadata = {
        "truth_policy": {},
        "observation_config": {},
        "noise_config": {},
        "export_policy": {},
        "research": {},
    }
    if isinstance(case, DatasetCase):
        metadata = {
            "truth_policy": case.truth_policy,
            "observation_config": case.observation_config,
            "noise_config": case.noise_config,
            "export_policy": case.export_policy,
            "research": case.research,
        }
        return explicit_name or case.name, case.config, metadata
    if isinstance(case, (str, Path)):
        raw = json.loads(Path(case).read_text(encoding="utf-8"))
        if "model_config" in raw:
            return _load_case_payload(load_dataset_case(case), explicit_name)
    if isinstance(case, dict) and "model_config" in case:
        metadata = {
            "truth_policy": dict(case.get("truth_policy", {})),
            "observation_config": dict(case.get("observations", case.get("observation_config", {}))),
            "noise_config": dict(case.get("noise", case.get("noise_config", {}))),
            "export_policy": dict(case.get("export_policy", {})),
            "research": dict(case.get("research", {})),
        }
        return explicit_name or str(case.get("name", "research_case")), dict(case["model_config"]), metadata
    config = _load_config(case)
    return explicit_name or _default_name(case, config), config, metadata


def _load_config(case: str | Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(case, dict):
        if "model_config" in case:
            return dict(case["model_config"])
        return case
    raw = json.loads(Path(case).read_text(encoding="utf-8"))
    if "model_config" in raw:
        return load_dataset_case(case).config
    return raw


def _default_name(case: str | Path | dict[str, Any], config: dict[str, Any]) -> str:
    if isinstance(case, (str, Path)):
        return Path(case).stem
    return str(config.get("name", config.get("model", {}).get("type", "research_case")))


def _dataset_index_entry(output_root: Path, dataset_path: Path) -> dict[str, Any]:
    root = dataset_path
    manifest = _read_json(root / "manifest.json")
    observation = _read_json(root / "metadata" / "observation.json")
    derived = _read_json(root / "metadata" / "derived.json")
    structural = _read_json(root / "truth" / "structural_properties.json")
    relative_path = _relative_dataset_path(output_root, root)
    return {
        "name": str(manifest["name"]),
        "path": relative_path,
        "dataset_type": str(manifest["dataset_type"]),
        "model_type": str(manifest["model_type"]),
        "backend": str(manifest["backend"]),
        "config_hash_sha256": str(manifest["config_hash_sha256"]),
        "model_config_hash_sha256": str(manifest.get("model_config_hash_sha256", manifest["config_hash_sha256"])),
        "dataset_config_hash_sha256": str(manifest.get("dataset_config_hash_sha256", manifest["config_hash_sha256"])),
        "research": manifest.get("research", {}),
        "noise": manifest.get("noise", {"configured": bool(manifest.get("noise_config", {}))}) | {
            "config": manifest.get("noise_config", {}),
        },
        "content_summary": manifest.get("content_summary", {}),
        "truth": {
            "time_steps": int(structural["time_steps"]),
            "dof_count": int(structural["dof_count"]),
            "response_shape": structural["response_shape"],
            "matrix_source": structural.get("matrix_source"),
            "modal_source": structural.get("modal_source"),
            "response_source": structural.get("response_source"),
            "backend_modal_source": structural.get("backend_modal_source"),
        },
        "observations": {
            "channel_count": int(observation["channel_count"]),
            "physical_channel_count": int(observation["physical_channel_count"]),
            "virtual_channel_count": int(observation["virtual_channel_count"]),
            "files": observation.get("files", {}),
        },
        "derived": {
            "quantity_count": int(derived.get("quantity_count", 0)),
            "quantity_ids": [
                str(quantity["id"])
                for quantity in derived.get("quantities", [])
            ],
        },
    }


def _relative_dataset_path(output_root: Path, dataset_path: Path) -> str:
    try:
        return dataset_path.relative_to(output_root).as_posix()
    except ValueError:
        return dataset_path.as_posix()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


__all__ = [
    "build_research_dataset_index",
    "generate_research_cases",
    "generate_research_dataset",
    "reset_output_dir",
    "write_research_dataset_index",
]
