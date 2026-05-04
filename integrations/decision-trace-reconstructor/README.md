# Decision Trace Reconstructor integration

This directory ships the canonical artefacts for running the
[Decision Trace Reconstructor](https://github.com/governance-evidence/decision-trace-reconstructor)
(DTR, Apache-2.0) `generic-jsonl` adapter on Operational Evidence Plane
example artefacts. Downstream readers can invoke DTR on OEP without
re-deriving the JSONL stream, the mapping config, or the allowed-scenario
expected output.

## Files

| File | Role |
|---|---|
| [`scripts/to_dtr_jsonl.py`](scripts/to_dtr_jsonl.py) | Converts OEP example JSONs (release manifest, agent-step event, OPA-backed permission packet, optional replay handle, deterministic eval) into a JSONL stream consumable by DTR `generic-jsonl`. Records sorted by timestamp. |
| [`mapping.v0.yaml`](mapping.v0.yaml) | Canonical DTR `generic-jsonl` mapping config. Translates OEP record kinds (`manifest`, `prompt`, `policy`, `tool`, `state`, `human`, `final`) to DTR fragment kinds (`config_snapshot`, `agent_message`, `policy_snapshot`, `tool_call`, `state_mutation`, `human_approval`). |
| `code_review_agent.jsonl` | Generated JSONL stream for the `code_review_agent` scenario. Regenerable from `to_dtr_jsonl.py` + the upstream OEP example artefacts at any commit. |
| `code_review_agent_denied.jsonl` | Generated JSONL stream for the `code_review_agent_denied` scenario. This path has no replay-state record because the tool call is denied before state is generated; it is currently pinned as a JSONL projection regression artifact only. |
| `code_review_agent.expected_feasibility.json` | Pinned DTR `feasibility.json` output for regression-testing the DTR pipeline against the allowed `code_review_agent` scenario. |

## Quickstart

Prerequisites:

- Python 3.11+ (matches OEP's own pyproject baseline)
- Decision Trace Reconstructor v0.1.0+ installed in a virtual environment with the `[generic-jsonl]` extra (or no extra — the adapter is bundled by default).

```bash
# 1. Regenerate the JSONL stream from the OEP example artefacts.
python integrations/decision-trace-reconstructor/scripts/to_dtr_jsonl.py \
  --scenario code_review_agent \
  --out integrations/decision-trace-reconstructor/code_review_agent.jsonl

# 2. Validate the mapping against the JSONL.
decision-trace validate generic-jsonl \
  --mapping integrations/decision-trace-reconstructor/mapping.v0.yaml \
  --sample-from integrations/decision-trace-reconstructor/code_review_agent.jsonl

# 3. Ingest the JSONL into a fragments manifest.
decision-trace ingest generic-jsonl \
  --from-file integrations/decision-trace-reconstructor/code_review_agent.jsonl \
  --mapping integrations/decision-trace-reconstructor/mapping.v0.yaml \
  --scenario-id oep_code_review_agent \
  --out integrations/decision-trace-reconstructor/code_review_agent.fragments.json

# 4. Reconstruct + emit feasibility report and PROV-O graph.
decision-trace reconstruct \
  integrations/decision-trace-reconstructor/code_review_agent.fragments.json \
  --out integrations/decision-trace-reconstructor/code_review_agent.report \
  --jsonld
```

## Expected output for `code_review_agent`

The pinned scenario produces six fragments resolved into two decision units
with completeness 85.7%. Per-property categories from
[`code_review_agent.expected_feasibility.json`](code_review_agent.expected_feasibility.json):

| Decision Event Schema property | DTR category |
|---|---|
| `inputs` | `fully_fillable` |
| `policy_basis` | `fully_fillable` |
| `operator_identity` | `fully_fillable` |
| `authorization_envelope` | `fully_fillable` |
| `reasoning_trace` | `structurally_unfillable` |
| `output_action` | `fully_fillable` |
| `post_condition_state` | `fully_fillable` |

The `reasoning_trace` row is `structurally_unfillable` rather than `opaque`
because the public OEP `code_review_agent` example uses a deterministic
mocked LLM and therefore emits no model-generation fragment. A non-mock
extension of the OEP example (with an actual LLM call recorded as a
`model_generation` fragment) would replace `structurally_unfillable` with
`opaque` for that property and leave the other six rows unchanged.

## Regression coverage

`make check-dtr-jsonl` regenerates and diffs the JSONL projection for both
`code_review_agent` and `code_review_agent_denied`. `make validate-dtr`
performs the external DTR ingest/reconstruct/feasibility diff for the allowed
`code_review_agent` scenario, where the pinned feasibility output is committed.
The denied scenario remains projection-pinned until a corresponding DTR
`expected_feasibility.json` is generated and committed.

## Adding new scenarios

To extend this integration to a new OEP scenario:

1. Add the scenario's example artefacts under `manifest/examples/`,
   `events/examples/`, `permissions/examples/`, and `traces/examples/` in
   the upstream OEP repo, following the existing naming pattern.
2. Add a new entry to `SCENARIOS` in
   [`../../oep_verify/scenarios.py`](../../oep_verify/scenarios.py) listing the
   file paths and expected reconstruction semantics for the new scenario.
3. Regenerate the JSONL with `--scenario <new_name>`.
4. If the scenario is part of full DTR regression coverage, pin the resulting
   `expected_feasibility.json` alongside.

## Claim boundary

This integration is documentation, conversion code, and pinned outputs only.
It does not modify the Decision Trace Reconstructor, claim equivalence
between OEP and any vendor regime, or assert that OEP is a benchmark or
production-readiness artefact. The Operational Evidence Plane retains its
existing claim boundaries (see [main `README.md`](../../README.md) §
"Claim Boundaries").

## License

Apache-2.0, matching the rest of the Operational Evidence Plane repository.
