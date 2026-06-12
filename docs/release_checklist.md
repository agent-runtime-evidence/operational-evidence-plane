# Release Checklist

Use this checklist before publishing a public tag, GitHub release, Zenodo deposit, or package artifact.

## Required Checks

- [ ] Run `make clean-state`.
- [ ] After bumping the version, run `uv lock` and commit the refreshed `uv.lock` (`make check-lock` verifies freshness).
- [ ] Run `make verify`.
- [ ] Run `make test` after installing dev dependencies.
- [ ] Run `make coverage` and confirm coverage remains at or above the configured threshold.
- [ ] Run `make build-check` and confirm the root wheel and sdist both pass.
- [ ] Run `make validate-counterfactual-replay`.
- [ ] Run `make check-replay-determinism`.
- [ ] Confirm the root sdist contains docs, canonical schemas/examples/scripts, tests, and CI metadata.
- [ ] Confirm the root sdist excludes generated replay state, counterfactual JSON/JSONL outputs, DTR intermediates, reports, and cache files.
- [ ] Confirm `git status --short` has no tracked changes.
- [ ] Confirm `demo/state/code_review_agent.sqlite` is ignored, not staged.
- [ ] Confirm `.github/workflows/verify.yml`, `SECURITY.md`, and `CITATION.cff` are present.
- [ ] Confirm `CONTRIBUTING.md` describes local checks, artifact updates, and claim boundaries.
- [ ] Confirm CI pins OPA to the intended tested 1.x version.
- [ ] Confirm README quickstart works from a fresh clone on a supported Python version.
- [ ] Confirm `pyproject.toml`, `CHANGELOG.md`, `CITATION.cff`, and the release tag use the same version/date.
- [ ] Confirm `project.urls` and GitHub repository metadata point to the public project.
- [ ] Review [public claims guide](public_claims.md).
- [ ] Confirm README and CHANGELOG include the v0.3 boundary statements: not a production-grade replay engine, not a compliance certification, not a substitute for vendor authorization-replay products, and not legal or regulatory adequacy by itself.
- [ ] Confirm Bedrock translation remains post-core documentation under `translations/bedrock/`.
- [ ] Confirm no AWS calls, live LLM calls, production APIs, or services are required.
- [ ] Confirm no `git tag`, GitHub release, or Zenodo action is run before explicit release approval.

## Release Boundary

The public Python distribution is the root package, `operational-evidence-plane`. Workspace member directories are source and development boundaries for the reference implementation; they are not independently published packages for this release line.

The current release line means:

- complete inspectable evidence chain;
- deterministic verification over committed artifacts;
- reproducible generated SQLite replay state;
- root wheel and source distribution checks;
- source-safe claim boundaries;
- optional Bedrock translation;
- counterfactual policy replay over stored decision records, when included in the release.

It does not mean production readiness, compliance readiness, standardization, legal-audit sufficiency, legal or regulatory adequacy, a vendor replacement, or a substitute for vendor authorization-replay products.

## v0.3 Counterfactual Replay Checks

- [ ] All three counterfactual demos pass through `make verify`.
- [ ] The v0.3 per-CR targets and `validate-composite` / `validate-backward-compat` pass through `make verify`.
- [ ] `make check-replay-determinism` passes with byte-identical SQLite state, counterfactual JSON/JSONL, and DTR JSONL across runs.
- [ ] README counterfactual wording is reviewed against `docs/public_claims.md`.
- [ ] `docs/architecture.md` distinguishes deterministic replay surfaces from evaluative model/cache-fresh-call estimates.
- [ ] `docs/decision_log.md` includes the v0.3 scope rows.
- [ ] `CHANGELOG.md` `[Unreleased]` is ready to be renamed to `v0.3.0 - YYYY-MM-DD` at release tag.

## Pre-Publication Privacy Pass

This repository is public; the planning context that produces each release scope is not. Every new doc edit, README change, CHANGELOG entry, code comment, and commit message must be scrubbed of private-context references before merge to `main` or release tag.

Strip before merge:

- **Local absolute paths.** No `/Users/<name>/`, no references to sibling repositories or planning directories outside this tree.
- **Private task identifiers.** No external task IDs, dated decision tags, or internal register entries — those live in private planning, not in public commits or docs.
- **Private rule citations.** No references to private feedback notes, strategy files, or memory-system entries in commit messages, doc text, or code comments.
- **Strategic «why».** Career / hiring-signal coupling, content-cadence rationale, paper-track sequencing, dated planning gates, competitive vendor maps — public docs justify decisions on engineering grounds (record-keeping requirements, replay correctness, integration surface), not on planning-calendar grounds.
- **Self-citation framing.** Repo docs use third-person artifact language («v0.1 shipped 2026-05-06») except where the README explicitly identifies the method paper as the author's own arXiv preprint. Avoid casual first-person release narration such as «as I shipped in v0.1».
- **Drafting noise.** Brainstorm tags, TODO-for-author comments, internal-question placeholders, and unresolved disagreements get resolved or removed before merge.

How to run the pass:

1. `git diff --staged` before each commit; scan the diff for absolute paths, external task IDs, and private file references.
2. Before tagging a release, re-read every file touched in this cycle (`CHANGELOG.md`, `README.md`, `docs/*.md`, source comments) for the patterns above.
3. If a private-context concept genuinely belongs in public docs, translate it to public language: «record-keeping requirements» instead of an internal article-citation chain, «landscape research suggests» instead of an internal research-task ID, «v0.1 release» instead of an internal milestone tag.

## Publication Steps

1. Create the release branch or commit after all required checks pass.
2. Ask for explicit approval before any release action.
3. Create an annotated tag for the release version only after approval.
4. Publish the GitHub release with the changelog summary and claim boundary only after approval.
5. Publish or accept the Zenodo deposit only after approval; if the GitHub→Zenodo integration mints it automatically, review the metadata before treating the release as complete.
6. After Zenodo emits the new DOI, update the README DOI badge and `CITATION.cff` to point at the new release archive.
7. If publishing to PyPI, publish only the root distribution for the current release line.
8. Verify the release artifact by installing it in a fresh virtual environment and running the packaged entry points.

## Files To Inspect Before Publication

1. `README.md`
2. `CHANGELOG.md`
3. `docs/architecture.md`
4. `docs/decision_log.md`
5. `docs/public_claims.md`
6. `SECURITY.md`
7. `CITATION.cff`
8. `CONTRIBUTING.md`
9. `pyproject.toml`
10. `playbooks/examples/code_review_reconstruction_packet.v0.json`
11. `translations/bedrock/source_notes.md`
