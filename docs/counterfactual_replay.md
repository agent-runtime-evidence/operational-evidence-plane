# Counterfactual Replay

The v0.3 branch adds counterfactual replay primitives over the stored decision record. Given a stored `decision_id`, the policy replay path reconstructs the recorded OPA input context from SQLite, substitutes a different policy bundle, re-runs OPA deterministically, and emits an original-vs-counterfactual decision diff that validates against [`replay/counterfactual_replay.v0.schema.json`](../replay/counterfactual_replay.v0.schema.json). Additional v0.3 paths record cost, reserve, five-surface drift, cache, and identity metadata under the same decision id.

```bash
oep replay pder_code_review_read_diff_0001 \
  --counterfactual \
  --policy-bundle permissions/policy/counterfactual/compound_reliability_step_bound.rego \
  --output-format json \
  --replay-timestamp-utc 2026-05-23T00:00:00Z
```

`OEP_REPLAY_MODE=counterfactual` enables the same mode from the environment. `--replay-timestamp-utc` pins the otherwise excluded wall-clock replay timestamp when comparing CLI JSON byte-for-byte; `--strip-exclusions` removes fields listed in `replay_metadata.determinism_exclusions` before printing JSON/JSONL output. `make validate-counterfactual-replay` regenerates the three counterfactual demos; `make check-replay-determinism` checks byte-identical SQLite state, counterfactual JSON/JSONL, and DTR JSONL across runs.

The three demos all extend the existing deterministic code-review fixture:

- compound reliability: a 10-step workflow replayed under a stricter 4-step bounded policy;
- budget-per-run cross-over: a synthetic runaway loop replayed under a stricter budget cap;
- approval-per-step escalation: a workflow replayed under a stricter write-approval policy.

The v0.3 decision metadata is additive under `decision_id`: permission,
cost, five-surface drift, cache, and identity sub-objects can be recorded
under one decision without making old records invalid. See
[Schema migration v0.3](schema_migration_v0.3.md) for the field list
and the backward-compatibility guarantee. The validation gates are exposed
as separate Make targets:

```bash
make validate-5surface-diff
make validate-cost-counterfactual
make validate-reserve-commit-release
make validate-cross-provider-drift
make validate-cache-substitution
make validate-identity-binding
make validate-composite
make validate-backward-compat
```

The composed CLI paths keep deterministic and evaluative replay separate:

```bash
oep diff pder_a pder_b --surface model,policy,prompt,tool,corpus
oep replay pder_code_review_read_diff_0001 \
  --substitute policy=permissions/policy/tool_permissions.rego \
  --substitute-budget per_run_cap_usd=0.005 \
  --substitute-model bedrock:anthropic.claude-opus-4-6 \
  --output-format json
oep reserve --budget-cap-usd 10 \
  --reservation bres_0001:6:4 \
  --reservation bres_0002:8:7
oep project --projected-cost-window 4:9 --budget-cap-usd 10 --approve
```

Policy, budget, reserve accounting, cache staleness, and config-surface
diffs are deterministic replays over recorded fields. Cross-provider model
substitution, cache substitution that implies a fresh model call, and
pre-session projection are labelled `replay_class: evaluative` and should
be read as counterfactual estimates.

Closest commercial precedents are [Styra DAS log-replay](https://docs.styra.com/das/observability-and-audit/decision-logs/log-replay) and [Permit.io Audit Log Replay](https://docs.permit.io/how-to/use-audit-logs/audit-log-replay). Both are useful authorization-domain precedents, but they are OPA/Rego-oriented, commercial-only products rather than an open-source, vendor-neutral, agent-runtime-decision-record-native reference implementation. The v0.3 branch demonstrates how the same replay shape can compose with agent runtime evidence records without claiming to replace those products.

[Srinivasan, "A Methodology for Selecting and Composing Runtime Architecture Patterns for Production LLM Agents"](https://arxiv.org/abs/2605.20173) (arXiv:2605.20173, 19 May 2026) is the Q2 2026 academic anchor for the Replay Divergence Problem: LLM-based consumers of deterministic logs can diverge under model-version or prompt changes. The v0.3 deterministic replay paths mitigate replay divergence for recorded policy, cost, cache-staleness, and config-surface fields. Cross-provider model substitution remains evaluative and does not re-execute the LLM call inside this reference implementation.

The Decision Evidence Maturity Model method specification that underlies the evidence-chain framing is my arXiv preprint at [arXiv:2605.04093](https://arxiv.org/abs/2605.04093) / DOI [`10.48550/arXiv.2605.04093`](https://doi.org/10.48550/arXiv.2605.04093). The v0.3 work implements deterministic policy, cost, reserve-accounting, cache-staleness, and five-surface config replay over recorded fields. Model substitution and cache substitution that implies a fresh model call are labelled evaluative estimates.

AAGATE ([arXiv:2510.25863](https://arxiv.org/abs/2510.25863)) is treated as complementary agent-governance work, not as a competitor. OEP's narrower scope is local evidence wiring and replay output over reference records. Reliability references such as Lusser's Law are used only as intuition for compounded workflow failure risk, not as empirical reliability proof for this repository.

Boundary: this is not a production-grade replay engine, not a compliance certification, not a substitute for vendor authorization-replay products, and does not constitute legal or regulatory adequacy by itself.
