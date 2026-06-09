# Incident Reconstruction Case Study

## Boundary

This is a synthetic case study over the shipped OEP v0.3.0 reference
implementation. It is an example, not a production incident, standard,
benchmark, employer-shipped system, compliance artifact, or legal/audit
claim.

## Incident Variant

The selected incident variant combines three pressures that tend to get
separated in ordinary demos:

1. An agent attempts an over-scoped destructive tool call.
2. A cost-runaway tail follows after repeated agent steps.
3. The run also carries a silent model-alias swap, which must be labelled as
   evaluative rather than deterministic replay.

The point is not that this synthetic incident happened. The point is that the
recorded evidence chain can answer the reconstruction questions without
inventing a new primitive.

## Reconstruction Question

When the incident review starts, the useful question is not just "what did the
trace show?" It is:

- Which version bundle governed the run?
- Which checkpoint and tool call were involved?
- Was the destructive action allowed or denied?
- What did the permission packet say, under which policy bundle?
- Would a prior budget cap have stopped the cost tail?
- Which parts are deterministic replay over recorded fields, and which parts
  are evaluative estimates?

## Evidence Packet

| Pattern field | OEP evidence |
|---|---|
| Time window | `2026-05-04T00:00:03Z` denied write event; generated budget replay timestamped by the deterministic demo runner |
| Affected checkpoint | `review.diff.write`, sequence 2, state `error` |
| Change ledger | `model_budget_counterfactual.v0.json` records model alias substitution and budget substitution |
| Actual-vs-shadow deltas | Permission packet records actual deny; budget replay records prior-cap counterfactual stop at step 6 |
| Version bundle | `manifest/examples/code_review_agent_release.v0.json` |
| Representative samples | `demo/fixtures/diff_synthetic_001.patch` and the denied write packet |
| Review impact | Denied destructive call blocks replay readiness for that branch; budget replay shows the cost tail would have been bounded |
| Rollback evidence | Release manifest rollback rules and reconstruction join order identify what must be present before claiming replay readiness |

## What The Evidence Answers

### Destructive Tool Call

The destructive branch is represented by:

- `events/examples/code_review_agent_denied_step.v0.json`
- `permissions/examples/code_review_tool_permission_denied.v0.json`
- `traces/examples/code_review_agent_denied_trace.v0.json`
- `playbooks/examples/code_review_denied_reconstruction_packet.v0.json`

The permission packet records `allow=false` and `matched_rule=deny_by_default`
for the mutable write operation. The reconstruction packet is intentionally
`blocked` because the denied tool call does not create SQLite replay state in
this reference demo.

Answer: the over-scoped destructive call would have been denied by the
reference policy path, but the denied path cannot claim deterministic replay
readiness.

### Cost-Runaway Tail

The budget replay output is:

- `examples/incident_reconstruction/counterfactual/budget_per_run_counterfactual.v0.json`
- `examples/incident_reconstruction/counterfactual/budget_per_run_counterfactual.v0.jsonl`

The replay records:

- original total: `47000`
- prior budget cap: `5000`
- termination step: `6`
- counterfactual total: `5000`
- termination code: `BUDGET_EXCEEDED`

Answer: under the prior budget cap, the synthetic runaway tail would have been
bounded at step 6.

### Silent Model-Alias Swap

The compact replay verdict is:

- `examples/incident_reconstruction/model_budget_counterfactual.v0.json`

It records a model surface change from
`deterministic-mock-reviewer@0.1.0` to
`bedrock:anthropic.claude-opus-4-6`.

This branch is labelled:

- `replay_metadata.replay_class=evaluative`
- `model_delta.counterfactual_label=counterfactual estimate`

Answer: the model-alias swap can be attributed as a changed surface, but the
cross-provider model substitution is not a deterministic "what would have
happened" claim.

## Public Claim Boundary

Safe wording:

- "This is one inspectable reference implementation of an incident
  reconstruction evidence packet."
- "The destructive tool call is denied by the reference OPA policy."
- "The cost replay shows a deterministic budget-cap replay over recorded
  fields."
- "The model substitution is evaluative and labelled as an estimate."

Do not say:

- "This is an incident standard."
- "This proves production readiness."
- "This is audit-ready or compliance-ready."
- "This is a benchmark."
- "The model substitution proves what would have happened."
- "Any employer shipped this exact architecture."

## Paper Gap

No preprint is spawned by default. The formal gap is only a parking-lot note:
if this example later needs a paper, first verify that the unresolved problem is
formal and role-relevant rather than just a stronger public write-up of the
reference implementation.

