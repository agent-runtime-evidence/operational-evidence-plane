# Public Claims Guide

Use this file before README, article, or external write-up wording changes.

## Allowed Claims

- Open, vendor-neutral reference implementation.
- Reference implementation, not framework.
- Demonstrates one wiring pattern among several plausible ones.
- Designed for inspectability and education first.
- Uses deterministic mocked LLM behavior, SQLite state, and real OPA decisions.
- Shows a small local chain from release manifest to reconstruction packet.
- Demonstrates a counterfactual policy replay primitive over stored decision records.
- Shows one inspectable policy-substitution replay path with byte-identical generated artifacts.
- Distinguishes deterministic replay over recorded fields from evaluative counterfactual estimates.
- Shows additive v0.3 metadata surfaces for cost, five-surface drift, cache provenance, and identity binding.
- Complements vendor-native agent versions, prompt registries, policy engines, telemetry specs, and communication protocols.
- Complements vendor-native authorization-replay products such as Styra DAS and Permit.io.

## Required Boundaries

- Not a vendor replacement.
- Not ready for production use.
- Not a production-grade replay engine.
- Not a standardization proposal.
- Not a compliance certification.
- Does not create compliance, audit readiness, or legal sufficiency by itself.
- Does not constitute legal or regulatory adequacy by itself.
- Not a substitute for vendor authorization-replay products.
- Not an agent framework, model gateway, tracing backend, policy language, eval platform, incident standard, or production postmortem system.
- Not a claim that no alternatives exist.
- Not a benchmark, model-quality claim, safety certification, or production monitoring result.

## Avoid These Claims

- "First" or "only" operational evidence plane.
- "Industry standard" or "emerging standard."
- "Replay ready for production use."
- "Production-grade counterfactual replay engine."
- "Compliance-ready replay engine."
- "Audit-ready evidence."
- "Proof of compliance."
- "Replaces Styra DAS, Permit.io, or OPA decision logs."
- "Replaces Bedrock, LangSmith, OTel, MCP, A2A, OPA, or cloud-native release tools."
- "Proves agent safety."
- "MCP formally adopts ID-JAG."
- "OEP cache fields are OpenTelemetry standard fields."
- "Evaluative model substitution shows what would have happened."

## Safer Positioning Paragraph

This repository is an open, vendor-neutral reference implementation for binding and reconstructing the operational evidence of agentic systems across release-time and runtime layers. It extends patterns already visible in vendor-native agent versions, prompt registries, policy engines, authorization-replay products, and telemetry specs, but does not replace them and does not claim standardization or production readiness. The safer novelty claim is that it demonstrates one inspectable way to stitch adjacent slices together, including deterministic policy, cost, and surface-diff replay over stored decision records while labelling model/cache-fresh-call substitutions as evaluative estimates.
