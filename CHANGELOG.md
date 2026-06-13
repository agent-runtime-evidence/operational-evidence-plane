# Changelog

All notable changes to this reference implementation are documented here.

## v0.3.2 - 2026-06-13

### Added

- Added `make check-lock`, a lockfile freshness gate wired into `make verify`
  (soft warning without `uv` locally; CI enforces via `uv sync --locked`),
  with `uv` carried as a locked dev dependency.
- Added a release workflow publishing the distribution to PyPI via trusted
  publishing on tag push; this release is the first PyPI publication.

### Changed

- Adopted `ruff format` across the codebase and enforce it in `make lint`
  (and therefore in the pre-commit hooks).
- Recomputed the release manifest workflow digest after the formatting pass
  touched bound demo sources; `release_manifest_version` is updated in the
  permission packet examples, the MCP and LangGraph adapter examples, and
  the packaged mirrors.

### Notes

- public API unchanged
- schema contract unchanged
- Manifest digests changed because bound workflow-source bytes changed;
  deterministic replay output remains byte-identical.

## v0.3.1 - 2026-06-12

### Added

- Added `make validate-human-review` to the `verify` chain: the
  human-review reconstruct and tamper-evidence demo now regenerates the
  committed `human_review_event.v0` examples deterministically and gates
  every verification run.
- Added a shared packaged-resource loader (`oep_verify.resources`) and
  shared script helpers in `oep_verify.verify_support` (`stable_json`,
  `eval_opa_decision`, `required_field`, `load_json_object_or_exit`,
  `read_only_sqlite_connection`), replacing duplicated copies across the
  per-package paths modules and validation scripts.
- Added pre-commit hooks bound to `make lint` and `make typecheck`, a
  Dependabot configuration for uv and GitHub Actions, and CI concurrency
  groups plus uv download caching.

### Changed

- Split the `oep_permissions.replay` monolith into a five-module package
  (`records`, `storage`, `wrapper`, `opa`, `surfaces`) behind unchanged
  import paths; all public names re-export from `oep_permissions.replay`.
- Collapsed the eight v0.3 feature gates into one `validate-v03-features`
  invocation in `verify`; the narrow targets remain as focused aliases.
- Derived the `coverage` target from the same Makefile validation targets
  as `verify` through a `PY_RUN` runner override, removing the manually
  duplicated coverage command list.
- Hoisted repeated identifier and digest regex patterns into per-schema
  `$defs` in the agent step event, human review event, tool permission
  packet, and operational trace schemas; validation semantics are
  unchanged.
- Recomputed the release manifest workflow and tool-schema digests after
  the bound workflow-source and schema bytes changed; updated
  `release_manifest_version` in the permission packet examples, the MCP
  and LangGraph adapter examples, and the packaged mirrors.

### Docs

- Restructured the README into a shorter landing page; moved the
  counterfactual replay deep dive, the record-keeping reference tables,
  and the landscape/prior-art sections under `docs/`.
- Added `docs/quickstart_walkthrough.md`, `docs/schema_reference.md`, and
  `docs/schema_versioning.md`; linked the release checklist from the
  README docs index.

### Quality

- Split the two test monoliths into nine domain modules with shared
  fixtures and helpers (`tests/conftest.py`, `tests/helpers.py`);
  parametrized the byte-identical counterfactual replay check.
- Kept the coverage gate at 95% and byte-identical replay determinism
  green across the refactor.

### Notes

- public API unchanged
- schema contract unchanged
- Manifest digests changed because bound workflow-source and schema bytes
  changed; deterministic replay output remains byte-identical. This
  release remains a bounded reference implementation: not a
  production-grade replay engine, not a compliance certification, not a
  vendor replacement, and not legal or regulatory adequacy by itself.
- Version metadata (the `pyproject.toml` bump, this changelog entry, and
  the citation date) landed in a follow-up commit after the v0.3.1 tag;
  the tagged tree archived under DOI 10.5281/zenodo.20667482
  self-identifies as 0.3.0 in `pyproject.toml`.

## v0.3.0 - 2026-05-24

### Added

- Added the counterfactual policy replay primitive: given a stored
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
- Added cross-provider drift counterfactual replay:
  `oep replay --substitute-model <provider:model_version>`. Output is
  labelled as evaluative replay (`replay_class: evaluative`); both
  the recorded estimate and the actual are retained.
- Added cost-bounded counterfactual replay:
  `oep replay --substitute-budget <policy>` re-evaluates each step
  under a substituted budget policy and reports the first step that
  would have been blocked. Added `per_step_cost_usd`,
  `per_step_cost_tokens`, `budget_cap_active`, and
  `budget_cap_source` fields.
- Added the reserve-commit-release cost-reservation lifecycle via
  `oep reserve`, and the pre-session projected-cost gate via
  `oep project --approve`. Added `budget_reservation_id`,
  `reservation_estimated_cost_usd`,
  `reservation_committed_cost_usd`,
  `reservation_excess_released_usd`, `reservation_outcome`, and
  `pre_session_projection_event` fields. The projection path emits
  the evaluative-replay marker.
- Added the 5-surface drift attribution diff and historical replay:
  `oep diff <decision_id_a> <decision_id_b> --surface
  model,policy,prompt,tool,corpus`, and extended substitution via
  `oep replay <id> --substitute
  model=...,policy=...,prompt=...,tool=...,corpus=...`. Added
  per-surface `before_version`, `after_version`, `change_class`,
  and `attribution_confidence` fields.
- Added cache-substitution counterfactual replay and cache-provenance
  fields: `oep replay <id> --substitute-cache-policy
  <staleness|embedding_version>` plus `cache_hit_id`,
  `cache_version`, `embedding_model_version`, `staleness_flag`,
  `cache_correctness_status`, `similarity_score`, and
  `invalidation_event_id` fields. Staleness-policy rejection is
  deterministic; cache→fresh-call substitution emits the
  evaluative-replay marker.
- Added the ID-JAG agent-identity integration: an agent-identity
  object bound into the approval-capture record alongside scoped
  credential lifetime. ID-JAG is cited as the IETF draft
  `draft-ietf-oauth-identity-assertion-authz-grant`, not as an
  adopted standard, and the MCP basic specification is NOT claimed
  to reference ID-JAG.
- Added a unified `decision_id` composite that joins policy,
  permission, cost, 5-surface drift, cache, and identity sub-objects
  into a single counterfactually replayable record, together with a
  composite integration test that runs a composed substitution
  (policy + budget + model) over a fixture decision record carrying
  all six sub-objects.
- Bumped schema to `schema_version: "0.3"` with additive, optional
  field additions across cost, cache, identity, and the 5-surface
  drift namespace. v0.2 records continue to validate and replay
  against the v0.3 schema; absent surfaces are reported as
  "not recorded" rather than as errors. Migration documented in
  `docs/schema_migration_v0.3.md`.
- Added `make validate-counterfactual-replay`,
  `make check-replay-determinism`, and
  `make validate-counterfactual-schema`, wired into `make verify`.
- Added `replay/scripts/check_v03_features.py` and the
  `validate-5surface-diff`, `validate-cost-counterfactual`,
  `validate-reserve-commit-release`,
  `validate-cross-provider-drift`, `validate-cache-substitution`,
  `validate-identity-binding`, `validate-composite`, and
  `validate-backward-compat` targets, all wired into `make verify`.
- Extended pytest coverage to policy substitution, CLI counterfactual
  mode, non-deterministic builtin cache injection, all three demos,
  schema validation, cross-run byte identity, denied-path replay
  state discipline, the five v0.3 feature checks (reserve,
  cross-provider, cache, identity, composite), and the
  backward-compat regression of v0.2 fixtures against the v0.3
  schema.
- Added the v0.3 documentation block: EU AI Act Articles
  19 / 26(6) / 50 / 73 mapping (education-only; no compliance
  claim); AAGATE (arXiv:2510.25863) framed as complementary, not
  competitor; MCP supply-chain non-claim statement; Replay
  Divergence Problem positioning hook (SDB arXiv:2605.20173);
  Lusser's Law reliability-arithmetic anchor; NIST AI RMF "1.0
  current (under revision); 1.1 via addenda / profiles" wording.

### Notes

- Counterfactual replay across the five substitution axes (policy,
  model, budget, cache, identity) is positioned as one inspectable
  demonstration that the v0.2 evidence chain composes into a
  unified, counterfactually replayable decision record. It is not a
  production-grade replay engine, not a compliance certification,
  not a substitute for vendor authorization-replay or observability
  products, and does not constitute legal or regulatory adequacy by
  itself.
- The non-determinism boundary is honest: policy / permission /
  budget substitution and 5-surface config diff produce
  deterministic "would / would-not have been allowed" outputs;
  cross-provider model substitution, cache→fresh-call substitution,
  and pre-session cost projection emit a `replay_class: evaluative`
  marker and record the substitution as a counterfactual estimate,
  not as a definitive re-derivation. This ties to the Replay
  Divergence Problem positioning hook (SDB arXiv:2605.20173).
- The closest commercial precedents are Styra DAS log-replay and
  Permit.io Audit Log Replay (policy domain); RunCycles
  (https://runcycles.io, Apache 2.0) ships the closest
  reserve-commit-release transactional cost model; SAFE-CACHE
  (PMC12894985), Krites / AVSC (arXiv:2602.13165), and the
  NDSS 2026 cache-poisoning research provide the academic substrate
  for the cache-correctness primitives. OEP keeps the combined
  implementation open-source, vendor-neutral, and native to agent
  runtime decision records.
- Per-claim caveats applied: cost incidents (the $47K agent loop,
  the $437 overnight loop, the Particula 847-step incident) are
  cited as practitioner-reported, single-source; OTel GenAI
  crypto-identity fields (`agent.trust_score`,
  `agent.drift_score`, `agent.scan_verdict`, Ed25519 as an OTel
  standard), MLflow GEPA / MIPRO / MemAlign tuning, and AWS
  AgentCore "graduated budget gates 50% / 75% / 90%" as shipped
  vendor features are NOT cited in this release.
- v0.2 records remain valid and replayable against the v0.3
  schema.

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
