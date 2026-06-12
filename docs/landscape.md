# Landscape and Prior Art

## Substitute Landscape

| Surface | Useful precedent | Boundary for this repository |
|---|---|---|
| Bedrock 5+ layers | Bedrock agent versions and aliases visibly bind foundation model, instructions, prompt templates, action groups, and knowledge-base associations; memory, guardrail, and runtime or collaboration configuration exist on adjacent surfaces. | Treat Bedrock as a strong vendor-native alias precedent. Do not claim vendors only bind four layers or fewer. |
| Azure `azure-ai-projects` 2.1.0 | Azure AI Projects SDK consolidation gives a current Foundry project surface, with 2.1.0 as the verified version anchor from 2026-04-20. | Useful SDK/platform integration, but not a named cross-stack release manifest with runtime replay and incident joins. |
| Vertex | Vertex `ReasoningEngine` and related Google Cloud surfaces expose deployment, model, evaluation, memory, RAG/search, and IAM concepts across separate resources. | A partial resource-binding precedent, not a single vendor-neutral release/runtime evidence artifact. |
| LangSmith | LangSmith Deployment supports managed deployments and revisions; LangSmith prompts support commit history, staging / production environments, rollback, tags, and the public prompt hub. | Strong observability, deployment, and prompt-management precedent, but split from permission packet, replay protocol, and incident playbook scope. |
| Styra DAS / Permit.io | Authorization-domain log replay re-evaluates historical OPA/Rego decisions against changed policy or data. | Closest commercial replay precedent, but not an agent-runtime decision-record chain and not a product this repository replaces. |
| OTel GenAI | OpenTelemetry GenAI semantic conventions describe runtime telemetry fields for generative AI systems. | Runtime telemetry substrate, not release management or cross-stack version binding. |
| MCP | Model Context Protocol defines tool and context communication patterns for agentic systems. | Runtime communication protocol, not a release manifest or incident reconstruction model. |
| A2A | Agent2Agent protocol defines inter-agent communication patterns. | Coordination protocol, not release-time binding, rollback, or replay evidence. |

## Prior Art

- Sovereign Agentic Loops: Decoupling AI Reasoning from Execution in Real-World Systems, arXiv:2604.22136, Jun He and Deying Yu, submitted 2026-04-24: [arxiv.org/abs/2604.22136](https://arxiv.org/abs/2604.22136).
  Paraphrased abstract: SAL argues that agents should not pass stochastic model outputs directly into mutating execution layers. It proposes a control-plane architecture where models emit structured intents with justifications, and those intents are validated against real system state and policy before execution, with evidence-chain support for audit and replay.
- Agent Control Protocol: Admission Control for Agent Actions, arXiv:2603.18829, Marcelo Fernandez, submitted 2026-03-19 and revised through v10 on 2026-04-30: [arxiv.org/abs/2603.18829](https://arxiv.org/abs/2603.18829).
  Paraphrased abstract: ACP addresses harmful behavior that can emerge across individually valid agent requests. It combines deterministic, history-aware admission control with static risk scoring and stateful signals such as anomaly accumulation and cooldown, so policy enforcement can account for execution traces rather than only isolated requests.

This repository treats SAL and ACP as legitimate prior conceptual work. The goal here is complementary engineering reference code and evidence wiring, not a competing theory or a claim of uniqueness.

## Adjacent Project Note

AgentReplay is an adjacent local-first desktop project for evals, observability, memory, and replay around agents and coding tools. It is not used as source code here: its desktop scope is different, and its AGPL-3.0 license is not compatible with this repository's permissive Apache-2.0 reuse boundary.

## Post-Core Translation

The Bedrock translation lives under [translations/bedrock/](../translations/bedrock/). It maps the vendor-neutral chain to Bedrock agent versions, aliases, action groups, prompt templates, memory/session state, and `InvokeAgent` trace references. It is documentation and mapping data only; it does not call AWS, deploy Bedrock resources, or make Bedrock the core implementation target.
