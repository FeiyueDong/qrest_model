"""Unified qREST model command line interface."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from qrest_model.backends import run_analysis
from qrest_model.backends.base import RIGID_FLOOR_SHEAR_3D, SHEAR_BUILDING_1D, dispatch_model_case
from qrest_model.common.compare import compare_master_arrays
from qrest_model.datasets import DATASET_CONFIG_ROOT, MODEL_ROOT, generate_all
from qrest_model.exporters.backend_outputs import write_shear_outputs, write_story3d_outputs
from qrest_model.exporters.qrest_dataset import (
    DEFAULT_CONFIG_SOURCE,
    DEFAULT_OUTPUT_ROOT,
    export_generated_cases,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qrest-model", description="Run and generate qREST model datasets.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a model case with a selected backend.")
    run_parser.add_argument("case", help="Path to JSON/YAML model config.")
    run_parser.add_argument("--backend", default="direct", choices=("direct", "opensees"))
    run_parser.add_argument("--output", default=None, help="Output directory for legacy backend files.")
    run_parser.set_defaults(func=_run_command)

    validate_parser = subparsers.add_parser("validate", help="Compare two backends for one model case.")
    validate_parser.add_argument("case", help="Path to JSON/YAML model config.")
    validate_parser.add_argument("--backend-a", default="direct", choices=("direct", "opensees"))
    validate_parser.add_argument("--backend-b", default="opensees", choices=("direct", "opensees"))
    validate_parser.add_argument("--output", default=None, help="Optional metrics text output path.")
    validate_parser.add_argument("--tolerance", type=float, default=None, help="Fail if any metric exceeds this value.")
    validate_parser.set_defaults(func=_validate_command)

    generate_parser = subparsers.add_parser("generate-datasets", help="Generate configured qREST model datasets.")
    generate_parser.add_argument("--output-root", default=str(MODEL_ROOT / "output" / "test_datasets"))
    generate_parser.add_argument("--config-root", default=str(DATASET_CONFIG_ROOT))
    generate_parser.add_argument("--case", action="append", help="Generate only the selected case. May be repeated.")
    generate_parser.set_defaults(func=_generate_datasets_command)

    export_parser = subparsers.add_parser("export-qrest", help="Export generated datasets to qREST text format.")
    export_parser.add_argument("--input", required=True, help="Generated dataset dir, or root containing generated cases.")
    export_parser.add_argument("--output", default=str(DEFAULT_OUTPUT_ROOT))
    export_parser.add_argument("--config-source", default=DEFAULT_CONFIG_SOURCE)
    export_parser.set_defaults(func=_export_qrest_command)

    return parser


def _run_command(args: argparse.Namespace) -> int:
    result = run_analysis(args.case, backend=args.backend)
    legacy = result.to_legacy_dict()
    output = Path(args.output) if args.output else _default_run_output(args.case, args.backend)
    if _case_model_type(args.case) == SHEAR_BUILDING_1D:
        write_shear_outputs(legacy, output)
    else:
        if result.metadata.backend == "opensees_story":
            legacy["stiffness_matrix_theory"] = legacy["stiffness_matrix"]
            write_story3d_outputs(legacy, output, stiffness_key="stiffness_matrix_theory")
        else:
            write_story3d_outputs(legacy, output)
    print(output)
    return 0


def _validate_command(args: argparse.Namespace) -> int:
    a = run_analysis(args.case, backend=args.backend_a).to_legacy_dict()
    b = run_analysis(args.case, backend=args.backend_b).to_legacy_dict()
    metrics = compare_master_arrays(a, b)
    text = _format_metrics(metrics)
    print(text)
    if args.output is not None:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    if args.tolerance is not None and any(value > args.tolerance for value in metrics.values()):
        return 1
    return 0


def _generate_datasets_command(args: argparse.Namespace) -> int:
    generated = generate_all(args.output_root, args.case, args.config_root)
    for path in generated:
        print(path)
    return 0


def _export_qrest_command(args: argparse.Namespace) -> int:
    config_source = args.config_source or None
    exported = export_generated_cases(args.input, args.output, config_source=config_source)
    for path in exported:
        print(path)
    return 0


def _default_run_output(case: str | Path, backend: str) -> Path:
    case_path = Path(case)
    family = "shear1d" if _case_model_type(case) == SHEAR_BUILDING_1D else "story3d"
    return MODEL_ROOT / "output" / family / case_path.stem / _backend_output_name(case, backend)


def _backend_output_name(case: str | Path, backend: str) -> str:
    model_type = _case_model_type(case)
    if backend == "opensees":
        return "opensees_shear" if model_type == SHEAR_BUILDING_1D else "opensees_story"
    return "direct_shear" if model_type == SHEAR_BUILDING_1D else "direct_stiffness"


def _case_model_type(case: str | Path) -> str:
    model_type, _payload = dispatch_model_case(case)
    if model_type not in {SHEAR_BUILDING_1D, RIGID_FLOOR_SHEAR_3D}:
        raise ValueError(f"Unsupported model.type: {model_type}")
    return model_type


def _format_metrics(metrics: dict[str, float]) -> str:
    return "\n".join(f"{key}: {value:.6e}" for key, value in metrics.items())


if __name__ == "__main__":
    raise SystemExit(main())
