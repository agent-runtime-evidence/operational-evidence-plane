# Changelog

All notable changes to this reference implementation are documented here.

## [Unreleased]

### Added

- Added the v0.3 counterfactual policy replay primitive: given a stored
  decision record from the v0.2 evidence chain, substitute a different
  policy bundle version retroactively and re-derive the discrete OPA
  decision that would have been made under the substituted policy.
- Added `OEP_REPLAY_MODE=counterfactual` and extended `oep replay` with
  `--counterfactual`, `--policy-bundle`, `--output-format`,
  `--replay-timestamp-utc`, and `--strip-exclusions` options.
- Added the counterfactual replay output schema
  (`replay/counterfactual_replay.v0.schema.json`) and packaged schema
  resource.
- Added optional `nd_builtin_cache` capture to the tool permission
  packet schema for deterministic injection of non-deterministic OPA
  builtin outputs during counterfactual replay.
- Added three counterfactual demos over the existing deterministic
  code-review fixture: compound reliability, budget-per-run cross-over,
  and approval-per-step escalation.
- Added `make validate-counterfactual-replay`,
  `make check-replay-determinism`, and
  `make validate-counterfactual-schema`, wired into `make verify`.
- Added pytest coverage for policy substitution, CLI counterfactual
  mode, non-deterministic builtin cache injection, all three demos,
  schema validation, cross-run byte identity, and denied-path replay
  state discipline.

### Notes

- Counterfactual replay is positioned as one inspectable demonstration
  of how the v0.2 evidence chain composes with retroactive policy
  substitution. It is not a production-grade replay engine, not a
  compliance certification, not a substitute for vendor
  authorization-replay products, and does not constitute legal or
  regulatory adequacy by itself.
- The closest commercial precedents are Styra DAS log-replay and
  Permit.io Audit Log Replay; both are OPA/Rego-oriented,
  commercial-only products in the authorization domain rather than
  agent-runtime replay engines. OEP v0.3 keeps the implementation
  open-source, vendor-neutral, and native to agent runtime decision
  records.
- Drift attribution and cache-substitution counterfactual demos remain
  v0.4 candidate design space.

## v0.2.0 - 2026-05-15

### Added

- Added v0.2 replayable permission trace fields to the OPA-backed tool
  permission packet schema (`scoped_credential_lifetime`,
  `approval_capture`, `policy_bundle_version`,
  `release_manifest_version`, `model_alias`, `resolved_model_version`,
  `model_provider`). Fields are additive and optional so v0.1 records
  continue to validate; the deterministic code-review demo populates
  them.
- Added the `oep` console script with a `replay <decision_id>`
  subcommand. The subcommand is a read-only reader over the existing
  SQLite replay store and reconstructs the recorded permission trace
  for a decision id (the `pder_*` packet identifier). It does not
  make live model or vendor API calls.
- Added an illustrative Model Context Protocol (MCP) adapter under
  `integrations/mcp/` with a mapping reference, synthetic envelope,
  and standalone projection script that translates an MCP
  `tools/call` envelope into an OEP permission packet.
- Added a README record-keeping reference table mapping OEP record
  fields to EU AI Act articles (Regulation (EU) 2024/1689) and
  NIST AI RMF 1.0 functions (GOVERN / MAP / MEASURE / MANAGE). The
  table is documentation and education only; it does not create a
  compliance or audit claim.
- Added `make validate-mcp` and `make validate-replay-cli` targets,
  wired into `make verify`.

### Notes

- This release does not change the previous boundary statements. It is
  still not ready for production use, not standardization, not proof of
  compliance, and not a vendor replacement.
- v0.1 records remain valid against the extended permission packet
  schema. The new fields are nullable / omittable for backward
  compatibility.

## v0.1.0 - 2026-05-06

Initial public release candidate for the Operational Evidence Plane reference implementation.

### Added

- Added a release manifest schema and code-review-agent release example.
- Added resolved model, prompt, tool schema, policy, workflow, rollout, eval, and data-state layer bindings with content digests.
- Added an agent-step event profile joined to the release manifest.
- Added an OPA-backed tool permission packet and executable policy check.
- Added an operational trace bundle and deterministic eval result.
- Added a deterministic code-review demo that regenerates local SQLite replay state.
- Added a reconstruction packet playbook over the full evidence chain.
- Added Decision Trace Reconstructor JSONL projection, mapping config, and pinned feasibility output for the allowed scenario.
- Added top-level `make regen-dtr-jsonl` and optional `make validate-dtr` targets.
- Added inspectability docs, public-claim guardrails, and release checklist.
- Added optional Bedrock translation notes and mapping data as post-core documentation.
- Added root sdist/wheel release guardrails for canonical resources, package resources, tests, CI metadata, and generated-artifact exclusions.
- Added GitHub Actions verification workflow, SECURITY.md, CITATION.cff, CONTRIBUTING.md, and pytest smoke tests for public-readiness hygiene.

### Notes

- Public API unchanged.
- Schema contract introduced.
- Public package boundary is the root `operational-evidence-plane` distribution; workspace directories are source and development boundaries for this release line.
- This release candidate is not ready for production use and does not create compliance readiness, legal-audit sufficiency, or standardization status.
