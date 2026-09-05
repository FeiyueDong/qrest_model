from __future__ import annotations

import argparse

from qrest_model.exporters.qrest_metadata import (
    build_qrest_metadata,
    build_qrest_metadata_from_files,
    count_csv_data_rows as _count_csv_data_rows,
    write_qrest_metadata,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate qREST-compatible metadata JSON from a model config.")
    parser.add_argument("--config", required=True, help="Path to model config.json.")
    parser.add_argument("--data", default=None, help="Optional CSV time-history file used to infer NPTS.")
    parser.add_argument("--output", required=True, help="Output metadata.json path.")
    parser.add_argument("--project-name", default="qREST_Model_Test")
    parser.add_argument("--event-name", default="MODEL_GENERATED")
    parser.add_argument("--provider", default="qREST_MODEL")
    parser.add_argument("--story-height", type=float, default=3.0)
    parser.add_argument("--base-elevation", type=float, default=0.0)
    args = parser.parse_args()

    metadata = build_qrest_metadata_from_files(
        args.config,
        data_path=args.data,
        project_name=args.project_name,
        event_name=args.event_name,
        provider=args.provider,
        story_height=args.story_height,
        base_elevation=args.base_elevation,
    )
    write_qrest_metadata(metadata, args.output)
    print(args.output)


__all__ = [
    "build_qrest_metadata",
    "build_qrest_metadata_from_files",
    "write_qrest_metadata",
    "_count_csv_data_rows",
    "main",
]


if __name__ == "__main__":
    main()
