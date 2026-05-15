# Changelog

All notable changes to this reference implementation are documented here.

## [Unreleased]

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

- This release does not change the v0.1.x boundary statements. It is
  still not production-ready, not standardization, not a compliance
  proof, and not a vendor replacement.
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
- This release candidate is not production-ready and does not create compliance readiness, legal-audit sufficiency, or standardization status.
