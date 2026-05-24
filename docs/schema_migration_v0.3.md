# Schema Migration v0.3

This note documents the additive v0.3 record fields. It is migration
documentation for the reference implementation, not a compliance or
production-readiness statement.

## Compatibility

The canonical schema file remains `tool_permission_packet.v0.schema.json`
because the changes are additive. Existing v0.1/v0.2 permission packets
that omit the new object still validate and still replay. The v0.3 replay
reader reports omitted sub-objects as `absent_surfaces` instead of treating
them as reconstruction errors.

`make validate-backward-compat` materializes a v0.2-style record by
removing the optional `decision_id` object from the demo packet, then
replays it with the v0.3 binary and checks the absent-surface report.

## Added Permission Packet Field

| Field | Required | Purpose |
|---|---:|---|
| `decision_id` | No | Optional v0.3 composite metadata object. |
| `decision_id.schema_version` | Yes, when `decision_id` is present | v0.3 metadata marker, currently `"0.3"`. |
| `decision_id.permission` | No | Joins the decision metadata back to permission packet, tool call, policy bundle, and approval capture reference. |
| `decision_id.cost` | No | Records per-step cost, token count, budget-cap state, reservation lifecycle, and pre-session projection fields. |
| `decision_id.drift` | No | Records five config drift surfaces: model, policy, prompt, tool registry, and retrieval corpus. |
| `decision_id.cache` | No | Records cache-hit provenance, embedding model version, staleness, correctness, similarity, and invalidation id. |
| `decision_id.identity` | No | Records agent identity, an ID-JAG draft binding, policy version, and approval-capture reference. |

## Cost Additions

`decision_id.cost` may contain:

| Field | Description |
|---|---|
| `per_step_cost_usd` | Recorded step cost in USD. |
| `per_step_cost_tokens` | Recorded token count for the step. |
| `budget_cap_active` | Whether a budget cap was active for the decision. |
| `budget_cap_source` | `per_session`, `per_tenant`, or `per_agent`. |
| `budget_reservation_id` | Reservation identifier for reserve-commit-release accounting. |
| `reservation_estimated_cost_usd` | Reserved estimate. |
| `reservation_committed_cost_usd` | Final committed cost. |
| `reservation_excess_released_usd` | Unused reserved amount released back to the budget. |
| `budget_cap_active_at_reservation_time` | Budget-cap state at reservation time. |
| `reservation_outcome` | `allowed`, `denied_budget_exhausted`, `denied_policy`, or `committed`. |
| `pre_session_projection_event` | Estimated cost window, approver identity, and approval outcome. |

## Drift Additions

`decision_id.drift` contains one optional object per surface:

| Surface | Object key | Change class |
|---|---|---|
| Model version | `model_version` | `alias_resolution` |
| Policy bundle | `policy_bundle` | `policy_update` |
| Prompt template | `prompt_template` | `prompt_edit` |
| Tool registry | `tool_registry` | `tool_added_removed` |
| Retrieval corpus | `retrieval_corpus` | `corpus_indexed` |

Each recorded surface object carries `before_version`, `after_version`,
`change_class`, and `attribution_confidence`.

## Cache Additions

`decision_id.cache` may contain `cache_hit_id`, `cache_version`,
`embedding_model_version`, `staleness_flag`,
`cache_correctness_status`, `similarity_score`, and
`invalidation_event_id`. These fields provide schema substrate for
cache-provenance replay. They are not an OpenTelemetry standard claim.

## Identity Additions

`decision_id.identity` may contain `agent_identity`, `id_jag_binding`,
`policy_version`, and `approval_capture_ref`. ID-JAG is treated as an
IETF draft binding reference, not as an adopted MCP requirement.

## Replay Classes

v0.3 counterfactual outputs may include
`replay_metadata.replay_class`:

| Replay class | Meaning |
|---|---|
| `deterministic` | Rule replay over recorded fields, such as policy, budget, reserve accounting, staleness rejection, or config-surface diff. |
| `evaluative` | Counterfactual estimate requiring a stochastic model execution or estimate, such as cross-provider model substitution, cache-to-fresh-call substitution, or pre-session projection. |

Evaluative outputs are labelled as estimates. They are not definitive
what-would-have-happened claims.
