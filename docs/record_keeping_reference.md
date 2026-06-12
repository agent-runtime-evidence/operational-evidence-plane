# Record-Keeping Reference

## Replayable Permission Trace Fields (added in v0.2, current in v0.3)

The v0.2 release extends the OPA-backed permission packet with optional
replayable permission trace fields. These fields are additive: v0.1
records that omit them still validate. The deterministic code-review
demo populates them so the v0.2 reproducibility walkthrough can show the
new primitives in use.

| Field | Description |
|---|---|
| `tool_call_id` | Identifier for the tool invocation event (also present in v0.1). |
| `scoped_credential_lifetime` | ISO 8601 time-to-live of the scoped credential used at the call (for example `PT15M`). |
| `approval_capture` | Captured human approval (if required), including approver identity, captured-at timestamp, and approval type. `null` when no human approval was required. |
| `policy_bundle_version` | `sha256:` hash of the policy bundle in effect at the call. Matches the release manifest's policy layer digest. |
| `release_manifest_version` | `sha256:` hash of the release manifest in effect at the call. |
| `model_alias` | Model alias as called by the agent (for example `claude-sonnet-4-6`). |
| `resolved_model_version` | Resolved underlying model version at call time. |
| `model_provider` | Provider of the model (for example `anthropic`, `openai`, `google`). |
| `nd_builtin_cache` | Optional replay cache for non-deterministic OPA builtin results such as time or HTTP lookups. `null` or omitted when no non-deterministic builtin capture is needed. |

The `model_*` fields are recorded because API providers can change
underlying model behavior under unchanged aliases. Recording the
resolved version and provider at call time keeps replay records stable
across silent provider-side model changes. This is a record-keeping
addition, not a model-quality claim.

The v0.2 fields are joined by the stable `pder_*` decision id (the
`packet_id` value) and the `replay_handle` primitives carried by the
v0.1 chain.

## Record-Keeping Reference Table

The table below maps OEP record fields to record-keeping requirements
named in well-known frameworks. It illustrates which event fields the
requirements describe; it is documentation and education, not a
compliance or audit claim. The repository does not create compliance,
audit readiness, or legal sufficiency by itself — see [the public
claims guide](public_claims.md) §Required Boundaries.

| OEP record field | EU AI Act event field cited | NIST AI RMF 1.0 function |
|---|---|---|
| `decision_id` + per-event timestamps | Article 12 (Record-keeping) | MEASURE function records |
| `policy_bundle_version` + `release_manifest_version` | Article 13 (Transparency and provision of information to deployers) | MEASURE function records |
| `approval_capture` (human-in-the-loop) | Article 14 (Human oversight) | MANAGE function records |
| Retention notes in README (not code) | Article 18 (Documentation keeping) | GOVERN function records |
| Replay trace as runtime evidence | Article 26(5) (deployer operational monitoring obligation) | MEASURE function records |

NIST AI RMF function-citation specificity is intentionally kept at the
four canonical function names (GOVERN / MAP / MEASURE / MANAGE) without
sub-function commitment. The NIST AI Risk Management Framework primary
source is version 1.0, released January 2023; the Generative AI Profile
(NIST AI 600-1, July 2024) is a separate companion document and is not
versioned as "1.1". Article numbers and titles refer to Regulation (EU)
2024/1689 (the EU AI Act). The table is reference material, not a
binding mapping.

The v0.3 planning notes also track an education-only EU AI Act timing
view for Articles 19, 26(6), 50, and 73. The source baseline is the
European Commission AI Act timeline and FAQ plus the Council/Parliament
Digital Omnibus political agreement announced on 7 May 2026; formal legal
texts remain the controlling source.

| Article | OEP-adjacent record topic | Timing note |
|---|---|---|
| 19 | Provider conformity-assessment evidence for high-risk systems | High-risk application dates are affected by the Digital Omnibus political agreement; planning notes should distinguish stand-alone and product-embedded high-risk systems. |
| 26(6) | Deployer log/evidence retention for high-risk use | Treat as high-risk-system planning material, not as an OEP compliance assertion. |
| 50 | Transparency records for AI-generated or AI-interaction disclosures | Transparency obligations are tracked separately from high-risk timing; some Article 50 timing details were addressed in the Digital Omnibus agreement. |
| 73 | Serious-incident reporting evidence | Incident evidence examples here are educational only and do not implement statutory reporting. |

Sources for the timing notes: [European Commission AI Act timeline](https://ai-act-service-desk.ec.europa.eu/en/ai-act/timeline/timeline-implementation-eu-ai-act), [European Commission AI Act FAQ](https://ai-act-service-desk.ec.europa.eu/en/faq), and [Council press release, 7 May 2026](https://www.consilium.europa.eu/en/press/press-releases/2026/05/07/artificial-intelligence-council-and-parliament-agree-to-simplify-and-streamline-rules/).

**Retention.** This repository is a reference implementation. It does
not retain runtime records on behalf of any deployer. Operators that
choose to reuse the schemas are responsible for record retention,
storage, access controls, and any legal requirements that apply to
their deployment context.
