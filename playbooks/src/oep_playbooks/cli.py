"""Command-line checks for packaged reconstruction packets."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from oep_playbooks.paths import DENIED_EXAMPLE_PATH, EXAMPLE_PATH, SCHEMA_PATH


def check_reconstruction_packets(schema_path: Path, packet_paths: Sequence[Path]) -> None:
    from oep_verify.verify_support import load_json_object, require, validate_json_schema

    schema = load_json_object(schema_path)
    for packet_path in packet_paths:
        packet = load_json_object(packet_path)
        validate_json_schema(schema, packet, instance_path=packet_path)
        require(
            packet.get("schema_version") == "oep.reconstruction_packet.v0",
            f"{packet_path} has bad schema_version",
        )
        require(
            packet.get("reconstruction_status") in {"ready", "blocked"},
            f"{packet_path} has bad reconstruction_status",
        )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Validate packaged OEP reconstruction packets.")
    parser.add_argument("--schema", type=Path, default=SCHEMA_PATH, help="Reconstruction packet JSON Schema path.")
    parser.add_argument(
        "--packet",
        type=Path,
        action="append",
        default=None,
        help="Reconstruction packet JSON path. May be repeated. Defaults to packaged examples.",
    )
    args = parser.parse_args(argv)

    packets = args.packet if args.packet is not None else [EXAMPLE_PATH, DENIED_EXAMPLE_PATH]
    check_reconstruction_packets(args.schema, packets)
    print("Reconstruction packet package checks passed")


if __name__ == "__main__":
    main()
