from __future__ import annotations

import argparse
import json
from pathlib import Path

from qrest_model.postprocess.master_mapping import map_sensors


def main() -> None:
    parser = argparse.ArgumentParser(description="Map model master time histories to configured sensor channels.")
    parser.add_argument("--config", required=True, help="Path to model config.json with sensors.")
    parser.add_argument("--master-dir", required=True, help="Directory containing master acceleration/velocity/displacement CSV files.")
    parser.add_argument("--output-dir", required=True, help="Directory for mapped sensor time histories.")
    parser.add_argument("--metadata-output", default=None, help="Optional qREST metadata.json output path.")
    parser.add_argument("--project-name", default="qREST_Model_Test")
    parser.add_argument("--event-name", default="MODEL_GENERATED")
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    map_sensors(
        config,
        args.master_dir,
        args.output_dir,
        metadata_output=args.metadata_output,
        project_name=args.project_name,
        event_name=args.event_name,
    )
    print(args.output_dir)


__all__ = ["map_sensors", "main"]


if __name__ == "__main__":
    main()
