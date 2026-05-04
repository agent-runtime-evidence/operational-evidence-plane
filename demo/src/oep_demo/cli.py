"""Command-line entry point for the deterministic code-review demo."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from oep_demo import run_demo


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the deterministic local code-review demo.")
    parser.add_argument(
        "--state-path",
        type=Path,
        default=None,
        help="Optional SQLite output path. OEP_DEMO_STATE_PATH is also supported.",
    )
    args = parser.parse_args(argv)

    result = run_demo(args.state_path) if args.state_path is not None else run_demo()
    print(
        "Generated demo state: "
        f"{result.state_path} event={result.event_id} trace={result.trace_id} "
        f"findings={result.finding_count}"
    )


if __name__ == "__main__":
    main()
