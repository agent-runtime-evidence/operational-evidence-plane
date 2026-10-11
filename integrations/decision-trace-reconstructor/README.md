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
- Decision Trace Reconstructor 0.2.0 from the locally prepared release, or an explicitly pinned historical 0.1.x version. The generic-jsonl adapter is bundled by default. Version 0.2.0 is not yet published.

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

That file remains the unchanged historical 0.1.x expectation. The complete
0.2.0 CLI expectation is stored separately in
[`expected/v0.2.0/code_review_agent.feasibility.json`](expected/v0.2.0/code_review_agent.feasibility.json).
The property categories and completeness below are unchanged, but 0.2.0 adds
the `fragment-coverage-v2` contract and actor inventory. It returns null for
`dominant_mode` and `dominant_break`: several record producers alone do not
establish decision diffusion. This generic-jsonl projection remains untyped
coverage evidence; it does not opt into `decision-evidence-v1`.

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
`code_review_agent` scenario in a temporary directory. It checks the CLI version
before comparing the full output with the corresponding saved expectation:

```bash
make validate-dtr DTR=/path/to/decision-trace DTR_VERSION=0.2.0
make validate-dtr DTR=/path/to/old/decision-trace DTR_VERSION=0.1.0
```

Unknown versions and version/output mismatches fail rather than silently
replacing the historical contract.
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
