from __future__ import annotations

import argparse
from pathlib import Path
import sys

MODEL_ROOT = Path(__file__).resolve().parents[2]
if str(MODEL_ROOT) not in sys.path:
    sys.path.insert(0, str(MODEL_ROOT))

from qrest_model.backends.direct_shear import run


def main() -> None:
    parser = argparse.ArgumentParser(description="Run qREST one-direction direct shear model.")
    parser.add_argument("--config", required=True, help="Path to JSON/YAML shear model config.")
    parser.add_argument("--output", default=None, help="Output directory.")
    args = parser.parse_args()
    output = args.output or str(MODEL_ROOT / "output" / "shear1d" / Path(args.config).stem / "direct_shear")
    run(args.config, output)
    print(f"Direct shear output written to {output}")


if __name__ == "__main__":
    main()
