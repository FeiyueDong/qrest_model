"""Unified qREST model command line interface."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from qrest_model.backends import run_analysis
from qrest_model.backends.base import (
    EULER_BEAM_2D,
    RAYLEIGH_BEAM_2D,
    RIGID_FLOOR_SHEAR_3D,
    SHEAR_FLEXURE_BUILDING_2D,
    SHEAR_BUILDING_1D,
    TIMOSHENKO_BEAM_2D,
    dispatch_model_case,
)
from qrest_model.common.compare import compare_master_arrays
from qrest_model.datasets import (
    DATASET_CONFIG_ROOT,
    MODEL_ROOT,
    RESEARCH_CONFIG_ROOT,
    generate_all,
    generate_research_cases,
    generate_research_dataset,
)
from qrest_model.datasets.validation import validate_research_dataset, validate_research_dataset_collection
from qrest_model.exporters.backend_outputs import write_beam2d_outputs, write_shear_outputs, write_story3d_outputs
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
    validate_parser.add_argument("--abs-tol", type=float, default=None, help="Fail if any *_max_abs metric exceeds this value.")
    validate_parser.add_argument("--rel-tol", type=float, default=None, help="Fail if any *_relative_l2 metric exceeds this value.")
    validate_parser.add_argument(
        "--tolerance",
        type=float,
        default=None,
        help="Legacy shortcut applied to both --abs-tol and --rel-tol when they are not set.",
    )
    validate_parser.set_defaults(func=_validate_command)

    generate_parser = subparsers.add_parser("generate-datasets", help="Generate configured qREST model datasets.")
    generate_parser.add_argument("--output-root", default=str(MODEL_ROOT / "output" / "test_datasets"))
    generate_parser.add_argument("--config-root", default=str(DATASET_CONFIG_ROOT))
    generate_parser.add_argument("--case", action="append", help="Generate only the selected case. May be repeated.")
    generate_parser.set_defaults(func=_generate_datasets_command)

    export_parser = subparsers.add_parser("export-qrest", help="Export generated datasets to qREST text format.")
    export_parser.add_argument("--input", required=True, help="Generated dataset dir, or root containing generated cases.")
    export_parser.add_argument("--output", default=str(DEFAULT_OUTPUT_ROOT))
    export_parser.add_argument(
        "--config-source",
        default=DEFAULT_CONFIG_SOURCE,
        help=(
            "Optional qREST config directory to copy. "
            "By default configs are regenerated from monitoring metadata without truth leakage."
        ),
    )
    export_parser.set_defaults(func=_export_qrest_command)

    research_parser = subparsers.add_parser("generate-research", help="Generate one research dataset with truth and observations.")
    research_parser.add_argument("case", help="Path to JSON model config.")
    research_parser.add_argument("--backend", default="direct", choices=("direct", "opensees"))
    research_parser.add_argument("--output", default=None, help="Output directory. Defaults to output/research_datasets/<case-stem>.")
    research_parser.add_argument("--name", default=None, help="Research dataset name. Defaults to the case filename stem.")
    research_parser.add_argument("--validate", action="store_true", help="Validate the generated research dataset.")
    research_parser.set_defaults(func=_generate_research_command)

    research_cases_parser = subparsers.add_parser("generate-research-cases", help="Generate configured research datasets.")
    research_cases_parser.add_argument("--output-root", default=str(MODEL_ROOT / "output" / "research_datasets"))
    research_cases_parser.add_argument("--config-root", default=str(RESEARCH_CONFIG_ROOT))
    research_cases_parser.add_argument("--case", action="append", help="Generate only the selected research case. May be repeated.")
    research_cases_parser.add_argument("--backend", default="direct", choices=("direct", "opensees"))
    research_cases_parser.add_argument("--validate", action="store_true", help="Validate generated research datasets.")
    research_cases_parser.set_defaults(func=_generate_research_cases_command)

    return parser


def _run_command(args: argparse.Namespace) -> int:
    result = run_analysis(args.case, backend=args.backend)
    output = Path(args.output) if args.output else _default_run_output(args.case, args.backend)
    model_type = _case_model_type(args.case)
    if model_type == SHEAR_BUILDING_1D:
        write_shear_outputs(result, output)
    elif model_type in {EULER_BEAM_2D, RAYLEIGH_BEAM_2D, TIMOSHENKO_BEAM_2D, SHEAR_FLEXURE_BUILDING_2D}:
        write_beam2d_outputs(result, output)
    else:
        stiffness_key = "stiffness_matrix_theory" if result.metadata.backend == "opensees_story" else "stiffness_matrix"
        write_story3d_outputs(result, output, stiffness_key=stiffness_key)
    print(output)
    return 0


def _validate_command(args: argparse.Namespace) -> int:
    a = run_analysis(args.case, backend=args.backend_a)
    b = run_analysis(args.case, backend=args.backend_b)
    metrics = compare_master_arrays(a, b)
    text = _format_metrics(metrics)
    print(text)
    if args.output is not None:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    abs_tol = args.abs_tol if args.abs_tol is not None else args.tolerance
    rel_tol = args.rel_tol if args.rel_tol is not None else args.tolerance
    if _metrics_exceed_tolerance(metrics, abs_tol=abs_tol, rel_tol=rel_tol):
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


def _generate_research_command(args: argparse.Namespace) -> int:
    output = Path(args.output) if args.output else MODEL_ROOT / "output" / "research_datasets" / Path(args.case).stem
    generated = generate_research_dataset(args.case, output, name=args.name, backend=args.backend)
    print(generated)
    if args.validate:
        metrics = validate_research_dataset(generated)
        print(_format_research_metrics(metrics))
    return 0


def _generate_research_cases_command(args: argparse.Namespace) -> int:
    generated = generate_research_cases(
        args.output_root,
        args.case,
        args.config_root,
        backend=args.backend,
    )
    for path in generated:
        print(path)
        if args.validate:
            print(_format_research_metrics(validate_research_dataset(path)))
    if args.validate:
        print(_format_research_metrics(validate_research_dataset_collection(args.output_root)))
    return 0


def _default_run_output(case: str | Path, backend: str) -> Path:
    case_path = Path(case)
    model_type = _case_model_type(case)
    if model_type == SHEAR_BUILDING_1D:
        family = "shear1d"
    elif model_type in {EULER_BEAM_2D, RAYLEIGH_BEAM_2D, TIMOSHENKO_BEAM_2D, SHEAR_FLEXURE_BUILDING_2D}:
        family = "beam2d"
    else:
        family = "story3d"
    return MODEL_ROOT / "output" / family / case_path.stem / _backend_output_name(case, backend)


def _backend_output_name(case: str | Path, backend: str) -> str:
    model_type = _case_model_type(case)
    if backend == "opensees":
        if model_type == SHEAR_BUILDING_1D:
            return "opensees_shear"
        if model_type == EULER_BEAM_2D:
            return "opensees_euler"
        if model_type == RAYLEIGH_BEAM_2D:
            return "opensees_rayleigh"
        if model_type == TIMOSHENKO_BEAM_2D:
            return "opensees_timoshenko"
        if model_type == SHEAR_FLEXURE_BUILDING_2D:
            return "opensees_shear_flexure"
        return "opensees_story"
    if model_type == SHEAR_BUILDING_1D:
        return "direct_shear"
    if model_type == EULER_BEAM_2D:
        return "direct_euler"
    if model_type == RAYLEIGH_BEAM_2D:
        return "direct_rayleigh"
    if model_type == TIMOSHENKO_BEAM_2D:
        return "direct_timoshenko"
    if model_type == SHEAR_FLEXURE_BUILDING_2D:
        return "direct_shear_flexure"
    return "direct_stiffness"


def _case_model_type(case: str | Path) -> str:
    model_type, _payload = dispatch_model_case(case)
    if model_type not in {
        SHEAR_BUILDING_1D,
        RIGID_FLOOR_SHEAR_3D,
        EULER_BEAM_2D,
        RAYLEIGH_BEAM_2D,
        TIMOSHENKO_BEAM_2D,
        SHEAR_FLEXURE_BUILDING_2D,
    }:
        raise ValueError(f"Unsupported model.type: {model_type}")
    return model_type


def _format_metrics(metrics: dict[str, float]) -> str:
    return "\n".join(f"{key}: {value:.6e}" for key, value in metrics.items())


def _format_research_metrics(metrics: dict[str, object]) -> str:
    return "\n".join(f"{key}: {value}" for key, value in metrics.items())


def _metrics_exceed_tolerance(
    metrics: dict[str, float],
    *,
    abs_tol: float | None,
    rel_tol: float | None,
) -> bool:
    for key, value in metrics.items():
        if key.endswith("_max_abs") and abs_tol is not None and value > abs_tol:
            return True
        if key.endswith("_relative_l2") and rel_tol is not None and value > rel_tol:
            return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())
