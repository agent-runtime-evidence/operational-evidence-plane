"""`oep` top-level command dispatcher.

Provides the v0.2 `oep replay <decision_id>` subcommand. Additional
subcommands may be added here in later releases.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

_DISPATCH_EPILOG = """\
Examples:
  # Reconstruct the demo's allowed decision (after `oep-run-demo`).
  oep replay pder_code_review_read_diff_0001

  # Print only the v0.2 model alias for a recorded decision.
  oep replay pder_code_review_read_diff_0001 --field model_alias

  # Read from an alternate SQLite path.
  oep replay pder_code_review_read_diff_0001 --state-path /tmp/oep.sqlite
"""

_REPLAY_EPILOG = """\
Examples:
  # Full reconstructed record as JSON.
  oep replay pder_code_review_read_diff_0001

  # Specific fields only (may be repeated).
  oep replay pder_code_review_read_diff_0001 \\
      --field decision_id --field policy_bundle_version

  # Custom state path (also supports OEP_DEMO_STATE_PATH env var).
  oep replay pder_code_review_read_diff_0001 --state-path /tmp/oep.sqlite

Denied decisions:
  Denied tool calls do not generate SQLite replay state by design — the
  v0.1 evidence chain marks replay state as missing for those events.
  Inspect the denied permission packet artifact (under
  permissions/examples/) directly instead of using `oep replay`.
"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oep",
        description=(
            "Operational Evidence Plane CLI. Subcommands operate on locally "
            "regenerable replay state; they do not make live model calls or "
            "vendor API calls."
        ),
        epilog=_DISPATCH_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    replay_parser = subparsers.add_parser(
        "replay",
        help=(
            "Reconstruct the recorded permission trace for a decision id from "
            "local SQLite replay state."
        ),
        description=(
            "Reconstruct the recorded permission trace for a decision id "
            "(the `pder_*` packet identifier) from the local SQLite replay "
            "state. The output joins the permission packet, agent-step event, "
            "trace bundle, and release-manifest summary recorded for that "
            "decision. The command is a read-only reader over the demo "
            "replay store; it does not call live models or vendor APIs."
        ),
        epilog=_REPLAY_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    replay_parser.add_argument(
        "decision_id",
        help="Decision identifier (the permission packet `pder_*` id).",
    )
    replay_parser.add_argument(
        "--state-path",
        type=Path,
        default=None,
        help=(
            "Path to the SQLite replay state. Defaults to the demo state "
            "(demo/state/code_review_agent.sqlite), overridable via "
            "OEP_DEMO_STATE_PATH."
        ),
    )
    replay_parser.add_argument(
        "--field",
        action="append",
        default=None,
        help=(
            "Optional record field to print on its own line instead of the "
            "full JSON record. May be repeated."
        ),
    )
    return parser


def _replay(args: argparse.Namespace) -> None:
    from oep_demo.paths import STATE_PATH as DEFAULT_STATE_PATH
    from oep_permissions.replay import ReplayError, reconstruct_decision

    state_path = args.state_path if args.state_path is not None else DEFAULT_STATE_PATH
    try:
        record = reconstruct_decision(state_path, args.decision_id)
    except ReplayError as exc:
        raise SystemExit(str(exc)) from exc

    record_dict = record.to_dict()
    if args.field:
        for field in args.field:
            if field not in record_dict:
                raise SystemExit(f"unknown replay record field: {field}")
            print(json.dumps(record_dict[field], indent=2, sort_keys=True))
        return

    print(json.dumps(record_dict, indent=2, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "replay":
        _replay(args)
        return

    parser.error(f"unknown command: {args.command}")


if __name__ == "__main__":
    main(sys.argv[1:])
