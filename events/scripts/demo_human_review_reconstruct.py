#!/usr/bin/env python3
"""Offline demo: emit, reconstruct, and tamper-verify human_review_event.v0 records.

Runs with the standard library only (no project dependencies, no network), so it
can be executed directly:

    python3 events/scripts/demo_human_review_reconstruct.py

It demonstrates the claim behind ``human_review_event.v0``: a human review of an
AI decision is only a control if it is *reconstructable* and *tamper-evident*.
The demo:

  1. EMITS two review events (one approved, one rejected) over the existing
     code-review agent-step decision. Each binds, by sha256 digest, the reviewer
     (with authority), the exact context shown, and the reviewed decision.
  2. RECONSTRUCTS each review from stored telemetry alone and re-verifies the
     binding digest.
  3. TAMPERS with the context shown (and re-points the reviewed decision) and
     shows the binding verification FAILS CLOSED.

Digest convention matches ``oep_verify.verify_support.sha256_digest``
("sha256:" + hex of the file bytes).
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "events/schema/human_review_event.v0.schema.json"
REVIEWED_DECISION_PATH = REPO_ROOT / "events/examples/code_review_agent_step.v0.json"
DENIED_DECISION_PATH = REPO_ROOT / "events/examples/code_review_agent_denied_step.v0.json"
CONTEXT_PATH = REPO_ROOT / "events/examples/human_review/context_code_review.md"
EMIT_DIR = REPO_ROOT / "events/examples/human_review"
BINDING_ALGORITHM = "oep.human_review_binding.v0"

JsonObject = dict[str, Any]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def sha256_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def binding_digest(
    reviewed_decision_ref: JsonObject,
    reviewed_decision_digest: str,
    context_digest: str,
    reviewer: JsonObject,
    outcome: str,
) -> str:
    """Tamper-evident bind over decision + context + reviewer authority + outcome."""
    payload = {
        "reviewed_decision_ref": reviewed_decision_ref,
        "reviewed_decision_digest": reviewed_decision_digest,
        "context_digest": context_digest,
        "reviewer_id": reviewer["id"],
        "authority": reviewer["authority"],
        "outcome": outcome,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256_bytes(canonical)


def build_event(
    *,
    event_id: str,
    event_type: str,
    outcome: str,
    reviewer: JsonObject,
    reviewed_ref: JsonObject,
    reviewed_digest: str,
    context_digest: str,
    captured_at: str,
) -> JsonObject:
    return {
        "schema_version": "oep.human_review_event.v0",
        "event_id": event_id,
        "event_time": captured_at,
        "event_type": event_type,
        "reviewed_decision_ref": reviewed_ref,
        "reviewer": reviewer,
        "context_as_shown": {
            "sha256": context_digest,
            "ref": "events/examples/human_review/context_code_review.md",
            "media_type": "text/markdown",
        },
        "action": {"outcome": outcome, "captured_at": captured_at, "rationale_ref": None},
        "decision_binding": {
            "reviewed_decision_digest": reviewed_digest,
            "context_digest": context_digest,
            "binding_digest": binding_digest(
                reviewed_ref, reviewed_digest, context_digest, reviewer, outcome
            ),
            "algorithm": BINDING_ALGORITHM,
        },
        "env": {
            "release_manifest_id": "rmf_code_review_agent_2026_05_04_v0",
            "policy_bundle_version": None,
        },
        "links": {
            "reviewed_event_ref": "events/examples/code_review_agent_step.v0.json",
            "context_ref": "events/examples/human_review/context_code_review.md",
            "trace_ref": None,
        },
    }


def verify(
    event: JsonObject,
    *,
    reviewed_decision_path: Path,
    context_path: Path,
) -> tuple[bool, list[str]]:
    """Re-verify a stored review event against the referenced decision + context."""
    notes: list[str] = []
    ok = True
    binding = event["decision_binding"]
    reviewed_digest = sha256_file(reviewed_decision_path)
    context_digest = sha256_file(context_path)
    if reviewed_digest != binding["reviewed_decision_digest"]:
        ok = False
        notes.append("reviewed_decision_digest mismatch (decision record changed or re-pointed)")
    if context_digest != binding["context_digest"]:
        ok = False
        notes.append("context_digest mismatch (context shown was altered)")
    expected = binding_digest(
        event["reviewed_decision_ref"],
        reviewed_digest,
        context_digest,
        event["reviewer"],
        event["action"]["outcome"],
    )
    if expected != binding["binding_digest"]:
        ok = False
        notes.append("binding_digest mismatch (attestation no longer binds this decision+context+reviewer+outcome)")
    return ok, notes


def validate_against_schema(events: list[JsonObject]) -> None:
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ModuleNotFoundError:
        print("schema validation : SKIPPED (jsonschema not installed; structural emit only)")
        return
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    total = 0
    for event in events:
        errors = sorted(validator.iter_errors(event), key=lambda e: list(e.absolute_path))
        total += len(errors)
        for error in errors[:5]:
            print(f"  SCHEMA ERROR {list(error.absolute_path)}: {error.message}")
    print(f"schema validation : {'OK' if total == 0 else f'{total} error(s)'} "
          f"(against {SCHEMA_PATH.relative_to(REPO_ROOT)})")
    if total:
        raise SystemExit(2)


def main() -> int:
    reviewed = json.loads(REVIEWED_DECISION_PATH.read_text(encoding="utf-8"))
    reviewed_ref = {
        "event_id": reviewed["event_id"],
        "trace_id": reviewed["trace_id"],
        "span_id": reviewed["span_id"],
        "decision_record_ref": "events/examples/code_review_agent_step.v0.json",
    }
    reviewed_digest = sha256_file(REVIEWED_DECISION_PATH)
    context_digest = sha256_file(CONTEXT_PATH)
    captured_at = "2026-05-04T00:05:00Z"

    approver = {
        "type": "human",
        "id": "user_senior_reviewer_01",
        "display_name": "Senior Reviewer",
        "authority": {
            "role": "senior_code_reviewer",
            "basis": "RBAC:approve_merge",
            "scope": "repo:demo/* diff<=500loc",
        },
    }
    rejecter = {
        "type": "human",
        "id": "user_security_reviewer_02",
        "display_name": "Security Reviewer",
        "authority": {
            "role": "security_reviewer",
            "basis": "RBAC:block_merge",
            "scope": "org-wide security gate",
        },
    }

    approved = build_event(
        event_id="hrev_code_review_approved_0001",
        event_type="human_review.approved",
        outcome="approved",
        reviewer=approver,
        reviewed_ref=reviewed_ref,
        reviewed_digest=reviewed_digest,
        context_digest=context_digest,
        captured_at=captured_at,
    )
    rejected = build_event(
        event_id="hrev_code_review_rejected_0001",
        event_type="human_review.rejected",
        outcome="rejected",
        reviewer=rejecter,
        reviewed_ref=reviewed_ref,
        reviewed_digest=reviewed_digest,
        context_digest=context_digest,
        captured_at=captured_at,
    )

    EMIT_DIR.mkdir(parents=True, exist_ok=True)
    emitted = {
        EMIT_DIR / "human_review_approved.v0.json": approved,
        EMIT_DIR / "human_review_rejected.v0.json": rejected,
    }
    for path, event in emitted.items():
        path.write_text(json.dumps(event, indent=2) + "\n", encoding="utf-8")
    print(f"EMIT       : {len(emitted)} human_review_event.v0 records -> "
          f"{EMIT_DIR.relative_to(REPO_ROOT)}/")
    validate_against_schema(list(emitted.values()))

    print("\n== RECONSTRUCT (from stored telemetry only) ==")
    all_ok = True
    for path in emitted:
        event = json.loads(path.read_text(encoding="utf-8"))
        ok, notes = verify(event, reviewed_decision_path=REVIEWED_DECISION_PATH, context_path=CONTEXT_PATH)
        all_ok = all_ok and ok
        reviewer = event["reviewer"]
        authority = reviewer["authority"]
        ref = event["reviewed_decision_ref"]
        print(f"- {event['event_id']}")
        print(f"    reviewer : {reviewer['display_name']} "
              f"(role={authority['role']}; basis={authority['basis']}; scope={authority['scope']})")
        print(f"    decision : {ref['event_id']} (trace {ref['trace_id'][:8]}..., span {ref['span_id'][:8]}...)")
        print(f"    context  : {event['context_as_shown']['ref']} [{event['context_as_shown']['sha256'][:23]}...]")
        print(f"    outcome  : {event['action']['outcome']} at {event['action']['captured_at']}")
        print(f"    binding  : {'VERIFIED' if ok else 'FAILED'}")
        if notes:
            print(f"    notes    : {notes}")

    print("\n== TAMPER (must fail closed) ==")
    approved_event = json.loads((EMIT_DIR / "human_review_approved.v0.json").read_text(encoding="utf-8"))

    tamper_dir = Path(tempfile.mkdtemp(prefix="oep_human_review_tamper_"))
    tampered_ctx = tamper_dir / "context_tampered.md"
    tampered_ctx.write_bytes(
        CONTEXT_PATH.read_bytes()
        + b"\n<injected after the fact: reviewer was actually shown a different, redacted diff>\n"
    )
    ok_a, notes_a = verify(approved_event, reviewed_decision_path=REVIEWED_DECISION_PATH, context_path=tampered_ctx)
    print(f"- alter context shown : binding {'FAILED (correct, fail-closed)' if not ok_a else 'PASSED (WRONG!)'}")
    print(f"    {notes_a}")

    ok_b, notes_b = verify(approved_event, reviewed_decision_path=DENIED_DECISION_PATH, context_path=CONTEXT_PATH)
    print(f"- re-point decision   : binding {'FAILED (correct, fail-closed)' if not ok_b else 'PASSED (WRONG!)'}")
    print(f"    {notes_b}")

    print("\n== SUMMARY ==")
    success = all_ok and not ok_a and not ok_b
    print(f"reconstruct+verify : {'OK' if all_ok else 'FAIL'}")
    print(f"tamper context     : {'fails closed' if not ok_a else 'DID NOT FAIL'}")
    print(f"re-point decision  : {'fails closed' if not ok_b else 'DID NOT FAIL'}")
    print("RESULT             : "
          + ("PASS - human review is reconstructable AND tamper-evident"
             if success else "FAIL - claim not backed"))
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
