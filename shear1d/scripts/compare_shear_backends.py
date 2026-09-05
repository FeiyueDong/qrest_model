from __future__ import annotations

import argparse
from pathlib import Path
import sys

MODEL_ROOT = Path(__file__).resolve().parents[2]
if str(MODEL_ROOT) not in sys.path:
    sys.path.insert(0, str(MODEL_ROOT))

from qrest_model.common.compare import compare_master_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare qREST one-direction shear backend CSV files.")
    parser.add_argument("--case", required=True, help="Case output directory containing backend subdirs.")
    parser.add_argument("--a", default="direct_shear/master_response.csv")
    parser.add_argument("--b", default="opensees_shear/master_response.csv")
    parser.add_argument("--output", default=None, help="Optional path for saving comparison metrics.")
    args = parser.parse_args()
    case = Path(args.case)
    metrics = compare_master_csv(case / args.a, case / args.b)
    lines = [f"{key}: {value:.6e}" for key, value in metrics.items()]
    text = "\n".join(lines)
    print(text)
    if args.output is not None:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
