# Schema Reference

One table per question: which schemas exist, where their examples live, and
which Make target validates each pair. All schemas use JSON Schema draft
2020-12 and carry a `schema_version` constant of the form `oep.<name>.v0`.

| Schema | File | Examples | Validation target |
|---|---|---|---|
| Release manifest | [`manifest/schema/release_manifest.v0.schema.json`](../manifest/schema/release_manifest.v0.schema.json) | [`code_review_agent_release.v0.json`](../manifest/examples/code_review_agent_release.v0.json) | `make validate-manifest` |
| Agent step event | [`events/schema/agent_step_event.v0.schema.json`](../events/schema/agent_step_event.v0.schema.json) | [`code_review_agent_step.v0.json`](../events/examples/code_review_agent_step.v0.json), [denied](../events/examples/code_review_agent_denied_step.v0.json) | `make validate-events` |
| Human review event | [`events/schema/human_review_event.v0.schema.json`](../events/schema/human_review_event.v0.schema.json) | [`human_review_approved.v0.json`](../events/examples/human_review/human_review_approved.v0.json), [rejected](../events/examples/human_review/human_review_rejected.v0.json) | `make validate-human-review` |
| Tool permission packet | [`permissions/schema/tool_permission_packet.v0.schema.json`](../permissions/schema/tool_permission_packet.v0.schema.json) | [`code_review_tool_permission.v0.json`](../permissions/examples/code_review_tool_permission.v0.json), [denied](../permissions/examples/code_review_tool_permission_denied.v0.json) | `make validate-permissions` |
| Operational trace | [`traces/schema/operational_trace.v0.schema.json`](../traces/schema/operational_trace.v0.schema.json) | [`code_review_agent_trace.v0.json`](../traces/examples/code_review_agent_trace.v0.json), [denied](../traces/examples/code_review_agent_denied_trace.v0.json) | `make validate-traces` |
| Eval result | [`traces/schema/eval_result.v0.schema.json`](../traces/schema/eval_result.v0.schema.json) | [`code_review_agent_eval.v0.json`](../traces/examples/code_review_agent_eval.v0.json), [denied](../traces/examples/code_review_agent_denied_eval.v0.json) | `make validate-eval` |
| Reconstruction packet | [`playbooks/schema/reconstruction_packet.v0.schema.json`](../playbooks/schema/reconstruction_packet.v0.schema.json) | [`code_review_reconstruction_packet.v0.json`](../playbooks/examples/code_review_reconstruction_packet.v0.json), [denied](../playbooks/examples/code_review_denied_reconstruction_packet.v0.json) | `make validate-playbooks` |
| Counterfactual replay | [`replay/counterfactual_replay.v0.schema.json`](../replay/counterfactual_replay.v0.schema.json) | [incident reconstruction outputs](../examples/incident_reconstruction/counterfactual/), regenerated demos under `demo/counterfactual/` | `make validate-counterfactual-schema`, `make validate-counterfactual-replay` |

## Shared identifier and digest conventions

The identifier patterns below appear across schemas. Where a schema uses a
pattern more than once it is defined once in that schema's `$defs` block and
referenced with `$ref`; the literal patterns are kept byte-identical across
schemas.

| Convention | Pattern | Meaning |
|---|---|---|
| `rmf_*` | `^rmf_[a-z0-9][a-z0-9_-]*$` | Release manifest id. |
| `evt_*` | `^evt_[a-z0-9][a-z0-9_-]*$` | Agent step event id. |
| `pder_*` | `^pder_[a-z0-9][a-z0-9_-]*$` | Permission decision id (`packet_id`); the stored-decision join key for replay. |
| `tool_*` | `^tool_[a-z0-9][a-z0-9_-]*$` | Tool call id. |
| `approval_*` | `^approval_[a-z0-9][a-z0-9_-]*$` | Captured human approval id. |
| Trace id | `^[a-f0-9]{32}$` | W3C-trace-style 16-byte hex id. |
| Span id | `^[a-f0-9]{16}$` | 8-byte hex span id. |
| Digest | `^sha256:[a-f0-9]{64}$` | `sha256:` plus hex of the file bytes, matching `oep_verify.verify_support.sha256_digest`. |

## Join keys across the chain

- `release_manifest_id` joins every runtime record back to the release
  manifest.
- `trace_id` / `span_id` join events, permission packets, and trace bundles.
- `pder_*` (`packet_id` / `permission_packet_ref` / `decision_id`) joins the
  permission packet, the agent step, and all v0.3 counterfactual replay
  outputs recorded under the same stored decision.
- `policy_bundle_version` and `release_manifest_version` pin the policy and
  manifest bytes in effect at decision time.

## `additionalProperties` policy

Top-level record objects declare `"additionalProperties": false` so unknown
fields fail validation. Two deliberate extensibility points stay open
(`"additionalProperties": true`): `nd_builtin_cache`, whose keys mirror OPA
non-deterministic builtin shapes that may evolve, and `identity_delta`,
which defers to external identity-binding formats. Treat any other open
object as a schema bug.
