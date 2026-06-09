# Incident Reconstruction Case Study

This example assembles an incident-reconstruction case study from the shipped
OEP v0.3.0 reference implementation. It does not add a new runtime, schema, or
policy primitive.

## Scope Choices

- Incident variant: synthetic over-scoped destructive tool call plus a
  cost-runaway tail after a silent model-alias swap.
- Demo depth: schema-backed evidence package plus replay outputs, not a new app
  walkthrough.
- Public framing: narrative-led, with code references as supporting evidence.
- Claim boundary: reference implementation / example only. Not a standard,
  production incident record, employer-shipped system, benchmark, compliance
  artifact, or model-quality claim.

## Evidence Map

| Role | Artifact |
|---|---|
| Version bundle | `manifest/examples/code_review_agent_release.v0.json` |
| Destructive tool-call event | `events/examples/code_review_agent_denied_step.v0.json` |
| Tool-call permission packet | `permissions/examples/code_review_tool_permission_denied.v0.json` |
| Operational trace | `traces/examples/code_review_agent_denied_trace.v0.json` |
| Reconstruction packet | `playbooks/examples/code_review_denied_reconstruction_packet.v0.json` |
| Cost-runaway replay output | `counterfactual/budget_per_run_counterfactual.v0.json` |
| Cost-runaway JSONL steps | `counterfactual/budget_per_run_counterfactual.v0.jsonl` |
| Model+budget replay verdict | `model_budget_counterfactual.v0.json` |
| Case-study narrative | `case_study.md` |
| Machine-readable index | `evidence_index.v0.json` |

The SQLite replay state generated beside the counterfactual output is ignored by
git. Regenerate it with the commands below.

## Reproduce

From the repository root:

```bash
.venv/bin/python demo/scripts/run_code_review_demo.py
.venv/bin/python playbooks/scripts/check_reconstruction_packet.py --scenario code_review_agent_denied
.venv/bin/python demo/scripts/run_budget_per_run_counterfactual.py --output-dir examples/incident_reconstruction/counterfactual
.venv/bin/python -m oep_verify.cli replay pder_code_review_read_diff_0001 \
  --state-path demo/state/code_review_agent.sqlite \
  --substitute-budget per_run_cap_usd=0.005 \
  --substitute-model bedrock:anthropic.claude-opus-4-6 \
  --output-format json \
  --replay-timestamp-utc 2026-06-02T00:00:00Z
```

The destructive write branch validates as a blocked reconstruction because the
OPA-backed permission packet denies the tool call and no SQLite replay state is
created for that denied path. The cost branch validates as deterministic
budget replay over recorded fields. The model-substitution branch is labelled
`evaluative`.

