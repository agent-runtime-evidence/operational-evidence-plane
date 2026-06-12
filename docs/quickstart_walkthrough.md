# Quickstart Walkthrough

A first pass through the evidence chain in about five minutes. It assumes the
[Quickstart](../README.md#quickstart) setup is done: Python 3.11–3.14, OPA CLI
1.x on `PATH`, and the locked `uv` environment installed.

## 1. Run the full verification chain

```bash
make verify
```

This regenerates `demo/state/code_review_agent.sqlite` from the committed
artifacts, validates every schema/example pair, runs the OPA policy tests,
replays the three counterfactual demos, and checks byte-identical replay
determinism. Everything later in this walkthrough reads state produced here.

## 2. Inspect the release-time intent

Open [`manifest/examples/code_review_agent_release.v0.json`](../manifest/examples/code_review_agent_release.v0.json).
The `layer_bindings` object names the shipped configuration: model, prompt,
tool schema, policy, workflow, rollout, eval, and data state. Resolved
bindings carry `sha256:` digests over the bound files, so a runtime record
can be joined back to exactly this release.

## 3. Inspect one runtime step

Open [`events/examples/code_review_agent_step.v0.json`](../events/examples/code_review_agent_step.v0.json).
The join keys are the heart of the chain:

- `release_manifest_id` points back to the manifest above;
- `trace_id` / `span_id` join the trace bundle;
- `permission_packet_ref` (`pder_*`) names the OPA-backed permission decision;
- `replay_handle` says how to reconstruct the step from stored state.

The same `pder_*` value appears in
[`permissions/examples/code_review_tool_permission.v0.json`](../permissions/examples/code_review_tool_permission.v0.json)
as `packet_id` — that is the stored decision id used everywhere below.

## 4. Replay the recorded decision

```bash
oep replay pder_code_review_read_diff_0001
```

This is a read-only join over the SQLite replay state: the permission packet,
agent-step event, trace bundle, and release-manifest summary for that
decision id, reconstructed from rows written in step 1. Add
`--field policy_bundle_version` to print a single field.

## 5. Replay the same decision under a different policy

```bash
oep replay pder_code_review_read_diff_0001 \
  --counterfactual \
  --policy-bundle permissions/policy/counterfactual/compound_reliability_step_bound.rego \
  --output-format json \
  --replay-timestamp-utc 2026-05-23T00:00:00Z
```

The recorded OPA input context is re-evaluated under the substituted policy
bundle, and the output is an original-vs-counterfactual diff that validates
against [`replay/counterfactual_replay.v0.schema.json`](../replay/counterfactual_replay.v0.schema.json).
See the [counterfactual replay guide](counterfactual_replay.md) for the
budget, model, cache, and config-surface substitution paths.

## 6. Where to go next

- [Architecture walkthrough](architecture.md) — roles of each artifact layer.
- [Schema reference](schema_reference.md) — all schemas, examples, and
  validation targets in one table.
- [Incident reconstruction case study](../examples/incident_reconstruction/README.md)
  — the evidence chain applied to an incident narrative.
