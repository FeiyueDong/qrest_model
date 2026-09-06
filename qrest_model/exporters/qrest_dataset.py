"""qREST text dataset exporter."""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from typing import Any

from qrest_model.exporters.qrest_metadata import build_qrest_metadata

MODEL_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_SOURCE = None
DEFAULT_OUTPUT_ROOT = MODEL_ROOT / "output" / "qrest_datasets"


def export_dataset(
    input_dir: str | Path,
    output_dir: str | Path,
    *,
    config_source: str | Path | None = DEFAULT_CONFIG_SOURCE,
) -> Path:
    case_dir = Path(input_dir)
    target_dir = Path(output_dir)
    metadata_path = case_dir / "metadata.json"
    acceleration_path = case_dir / "time_history" / "acceleration.csv"
    if _is_research_dataset(case_dir):
        return export_research_dataset(case_dir, target_dir, config_source=config_source)
    if not metadata_path.exists():
        raise FileNotFoundError(f"Missing generated metadata: {metadata_path}")
    if not acceleration_path.exists():
        raise FileNotFoundError(f"Missing generated acceleration CSV: {acceleration_path}")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    channel_ids = _metadata_channel_ids(metadata)
    rows = _read_acceleration_rows(acceleration_path, channel_ids)
    expected_npts = int(metadata["DataInfo"]["NPTS"])
    if len(rows) != expected_npts:
        raise ValueError(
            f"{acceleration_path} has {len(rows)} rows, metadata NPTS is {expected_npts}."
        )

    target_dir.mkdir(parents=True, exist_ok=True)
    dataset_name = target_dir.name
    (target_dir / f"{dataset_name}_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _write_text_matrix(target_dir / f"{dataset_name}_data.txt", rows)

    source = Path(config_source) if config_source is not None else case_dir / "config"
    if source.exists():
        shutil.copytree(source, target_dir / "config", dirs_exist_ok=True)

    return target_dir


def discover_generated_cases(input_root: str | Path) -> list[Path]:
    root = Path(input_root)
    if _is_research_dataset(root):
        return [root]
    if (root / "metadata.json").exists() and (root / "time_history" / "acceleration.csv").exists():
        return [root]
    return sorted(
        path
        for path in root.iterdir()
        if path.is_dir()
        and (
            ((path / "metadata.json").exists() and (path / "time_history" / "acceleration.csv").exists())
            or _is_research_dataset(path)
        )
    )


def export_generated_cases(
    input_root: str | Path,
    output_root: str | Path,
    *,
    config_source: str | Path | None = DEFAULT_CONFIG_SOURCE,
) -> list[Path]:
    cases = discover_generated_cases(input_root)
    if not cases:
        raise FileNotFoundError(f"No generated model datasets found under: {input_root}")
    output_base = Path(output_root)
    return [
        export_dataset(case, output_base / case.name, config_source=config_source)
        for case in cases
    ]


def export_research_dataset(
    input_dir: str | Path,
    output_dir: str | Path,
    *,
    config_source: str | Path | None = DEFAULT_CONFIG_SOURCE,
) -> Path:
    case_dir = Path(input_dir)
    target_dir = Path(output_dir)
    manifest = json.loads((case_dir / "manifest.json").read_text(encoding="utf-8"))
    observation = json.loads((case_dir / "metadata" / "observation.json").read_text(encoding="utf-8"))
    config = json.loads((case_dir / "config.json").read_text(encoding="utf-8"))
    physical_files = observation.get("files", {}).get("physical", {})
    acceleration_relative = physical_files.get("acceleration")
    if acceleration_relative is None:
        raise ValueError("Research qREST export currently requires physical acceleration observations.")
    acceleration_path = case_dir / "observations" / str(acceleration_relative)
    channel_ids = [
        str(channel["id"])
        for channel in observation.get("channels", [])
        if channel.get("kind") == "physical" and channel.get("quantity") == "acceleration"
    ]
    rows = _read_acceleration_rows(acceleration_path, channel_ids)
    metadata = build_qrest_metadata(
        config,
        npts=len(rows),
        project_name=f"qREST_Model_{manifest['name']}",
        event_name=f"MODEL_{str(manifest['name']).upper()}",
    )
    if _metadata_channel_ids(metadata) != channel_ids:
        raise ValueError("Research qREST export metadata channel order does not match physical observations.")

    target_dir.mkdir(parents=True, exist_ok=True)
    dataset_name = target_dir.name
    (target_dir / f"{dataset_name}_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _write_text_matrix(target_dir / f"{dataset_name}_data.txt", rows)

    source = Path(config_source) if config_source is not None else case_dir / "config"
    if source.exists():
        shutil.copytree(source, target_dir / "config", dirs_exist_ok=True)

    return target_dir


def _metadata_channel_ids(metadata: dict[str, Any]) -> list[str]:
    channels = metadata["InstrumentInfo"]["Channels"]
    channel_ids = [str(channel["ChannelID"]) for channel in channels]
    channel_num = int(metadata["InstrumentInfo"]["ChannelNum"])
    if len(channel_ids) != channel_num:
        raise ValueError(
            f"Metadata ChannelNum is {channel_num}, but {len(channel_ids)} channels are defined."
        )
    return channel_ids


def _read_acceleration_rows(path: Path, channel_ids: list[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {path}")
        missing = [channel_id for channel_id in channel_ids if channel_id not in reader.fieldnames]
        if missing:
            raise ValueError(f"CSV is missing metadata channels: {missing}")
        for row in reader:
            rows.append([_require_numeric(row[channel_id], channel_id) for channel_id in channel_ids])
    return rows


def _require_numeric(value: str | None, channel_id: str) -> str:
    if value is None or value == "":
        raise ValueError(f"Missing value for channel {channel_id}.")
    float(value)
    return value


def _write_text_matrix(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(" ".join(row))
            handle.write("\n")


def _is_research_dataset(path: Path) -> bool:
    manifest_path = path / "manifest.json"
    metadata_dir = path / "metadata"
    if not manifest_path.exists() or not metadata_dir.exists():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return manifest.get("dataset_type") == "research"


__all__ = [
    "DEFAULT_CONFIG_SOURCE",
    "DEFAULT_OUTPUT_ROOT",
    "discover_generated_cases",
    "export_dataset",
    "export_generated_cases",
    "export_research_dataset",
]
