# Public Claims Guide

Use this file before README, article, or external write-up wording changes.

## Allowed Claims

- Open, vendor-neutral reference implementation.
- Reference implementation, not framework.
- Demonstrates one wiring pattern among several plausible ones.
- Designed for inspectability and education first.
- Uses deterministic mocked LLM behavior, SQLite state, and real OPA decisions.
- Shows a small local chain from release manifest to reconstruction packet.
- Complements vendor-native agent versions, prompt registries, policy engines, telemetry specs, and communication protocols.

## Required Boundaries

- Not a vendor replacement.
- Not production-ready.
- Not a standardization proposal.
- Does not create compliance, audit readiness, or legal sufficiency by itself.
- Not an agent framework, model gateway, tracing backend, policy language, eval platform, incident standard, or production postmortem system.
- Not a claim that no alternatives exist.
- Not a benchmark, model-quality claim, safety certification, or production monitoring result.

## Avoid These Claims

- "First" or "only" operational evidence plane.
- "Industry standard" or "emerging standard."
- "Production-ready replay."
- "Audit-ready evidence."
- "Compliance proof."
- "Replaces Bedrock, LangSmith, OTel, MCP, A2A, OPA, or cloud-native release tools."
- "Proves agent safety."

## Safer Positioning Paragraph

This repository is an open, vendor-neutral reference implementation for binding and reconstructing the operational evidence of agentic systems across release-time and runtime layers. It extends patterns already visible in vendor-native agent versions, prompt registries, policy engines, and telemetry specs, but does not replace them and does not claim standardization or production readiness. The safer novelty claim is that it demonstrates one inspectable way to stitch adjacent slices together.
