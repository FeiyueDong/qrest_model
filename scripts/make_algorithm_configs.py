from __future__ import annotations

import argparse

from qrest_model.exporters.algorithm_config import (
    PYTHON_HOME,
    write_algorithm_configs,
    write_algorithm_configs_for_root,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate qREST algorithm configs for generated model datasets.")
    parser.add_argument("--input", required=True, help="Generated dataset dir, or root containing generated cases.")
    args = parser.parse_args()

    for path in write_algorithm_configs_for_root(args.input):
        print(path)


__all__ = [
    "PYTHON_HOME",
    "write_algorithm_configs",
    "write_algorithm_configs_for_root",
    "main",
]


if __name__ == "__main__":
    main()
