from __future__ import annotations

import argparse
from pathlib import Path

from qrest_model.exporters.qrest_dataset import (
    DEFAULT_CONFIG_SOURCE,
    DEFAULT_OUTPUT_ROOT,
    discover_generated_cases,
    export_dataset,
    export_generated_cases,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export generated model datasets to qREST text dataset directories."
    )
    parser.add_argument("--input", required=True, help="Generated dataset dir, or root containing generated cases.")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_ROOT),
        help="Output root for qREST text dataset directories.",
    )
    parser.add_argument(
        "--config-source",
        default=DEFAULT_CONFIG_SOURCE,
        help=(
            "Optional qREST config directory to copy. "
            "By default configs are regenerated from monitoring metadata without truth leakage."
        ),
    )
    args = parser.parse_args()

    config_source = args.config_source or None
    exported = export_generated_cases(args.input, Path(args.output), config_source=config_source)
    for path in exported:
        print(path)


__all__ = [
    "DEFAULT_CONFIG_SOURCE",
    "DEFAULT_OUTPUT_ROOT",
    "discover_generated_cases",
    "export_dataset",
    "export_generated_cases",
    "main",
]


if __name__ == "__main__":
    main()
