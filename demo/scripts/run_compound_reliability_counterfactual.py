#!/usr/bin/env python3
"""Generate the v0.3 compound reliability counterfactual demo outputs."""

from __future__ import annotations

import argparse
from pathlib import Path

from oep_demo.counterfactual import DEFAULT_COUNTERFACTUAL_DIR, run_compound_reliability_counterfactual


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_COUNTERFACTUAL_DIR,
        help="Directory for generated counterfactual JSON/JSONL outputs.",
    )
    parser.add_argument(
        "--state-path",
        type=Path,
        default=None,
        help="Optional SQLite replay state path. Defaults inside --output-dir.",
    )
    args = parser.parse_args()

    result = run_compound_reliability_counterfactual(args.output_dir, state_path=args.state_path)
    print(
        "Generated compound reliability counterfactual: "
        f"{result.json_path} steps={result.total_steps} "
        f"first_divergent_step={result.first_divergent_step}"
    )


if __name__ == "__main__":
    main()
