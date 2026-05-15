# Release Checklist

Use this checklist before publishing a public `v0.1.x` tag, GitHub release, or package artifact.

## Required Checks

- [ ] Run `make clean-state`.
- [ ] Run `make verify`.
- [ ] Run `make test` after installing dev dependencies.
- [ ] Run `make coverage` and confirm coverage remains at or above the configured threshold.
- [ ] Run `make build-check` and confirm the root wheel and sdist both pass.
- [ ] Confirm the root sdist contains docs, canonical schemas/examples/scripts, tests, and CI metadata.
- [ ] Confirm the root sdist excludes generated replay state, DTR intermediates, reports, and cache files.
- [ ] Confirm `git status --short` has no tracked changes.
- [ ] Confirm `demo/state/code_review_agent.sqlite` is ignored, not staged.
- [ ] Confirm `.github/workflows/verify.yml`, `SECURITY.md`, and `CITATION.cff` are present.
- [ ] Confirm `CONTRIBUTING.md` describes local checks, artifact updates, and claim boundaries.
- [ ] Confirm CI pins OPA to the intended tested 1.x version.
- [ ] Confirm README quickstart works from a fresh clone on a supported Python version.
- [ ] Confirm `pyproject.toml`, `CHANGELOG.md`, `CITATION.cff`, and the release tag use the same version/date.
- [ ] Confirm `project.urls` and GitHub repository metadata point to the public project.
- [ ] Review [public claims guide](public_claims.md).
- [ ] Confirm Bedrock translation remains post-core documentation under `translations/bedrock/`.
- [ ] Confirm no AWS calls, live LLM calls, production APIs, or services are required.

## Release Boundary

The public Python distribution is the root package, `operational-evidence-plane`. Workspace member directories are source and development boundaries for the reference implementation; they are not independently published packages for `v0.1.x`.

`v0.1.x` means:

- complete inspectable evidence chain;
- deterministic verification over committed artifacts;
- reproducible generated SQLite replay state;
- root wheel and source distribution checks;
- source-safe claim boundaries;
- optional Bedrock translation.

It does not mean production readiness, compliance readiness, standardization, legal-audit sufficiency, or a vendor replacement.

## Pre-Publication Privacy Pass

This repository is public; the planning context that produces each release scope is not. Every new doc edit, README change, CHANGELOG entry, code comment, and commit message must be scrubbed of private-context references before merge to `main` or release tag.

Strip before merge:

- **Local absolute paths.** No `/Users/<name>/`, no references to sibling repositories or planning directories outside this tree.
- **Private task identifiers.** No external task IDs, dated decision tags, or internal register entries — those live in private planning, not in public commits or docs.
- **Private rule citations.** No references to private feedback notes, strategy files, or memory-system entries in commit messages, doc text, or code comments.
- **Strategic «why».** Career / hiring-signal coupling, content-cadence rationale, paper-track sequencing, dated planning gates, competitive vendor maps — public docs justify decisions on engineering grounds (record-keeping requirements, replay correctness, integration surface), not on planning-calendar grounds.
- **Self-citation framing.** Repo docs use third-person artifact language («v0.1 shipped 2026-05-06»), not first-person framing («as I shipped in v0.1»). First-person framing belongs to external content surfaces, not repo files.
- **Drafting noise.** Brainstorm tags, TODO-for-author comments, internal-question placeholders, and unresolved disagreements get resolved or removed before merge.

How to run the pass:

1. `git diff --staged` before each commit; scan the diff for absolute paths, external task IDs, and private file references.
2. Before tagging a release, re-read every file touched in this cycle (`CHANGELOG.md`, `README.md`, `docs/*.md`, source comments) for the patterns above.
3. If a private-context concept genuinely belongs in public docs, translate it to public language: «record-keeping requirements» instead of an internal article-citation chain, «landscape research suggests» instead of an internal research-task ID, «v0.1 release» instead of an internal milestone tag.

## Publication Steps

1. Create the release branch or commit after all required checks pass.
2. Create an annotated tag for the release version.
3. Publish the GitHub release with the changelog summary and claim boundary. The configured GitHub→Zenodo integration mints the release DOI automatically; no manual Zenodo step is required.
4. After Zenodo emits the new DOI, update the README DOI badge and `CITATION.cff` to point at the new release archive.
5. If publishing to PyPI, publish only the root distribution for the current release line.
6. Verify the release artifact by installing it in a fresh virtual environment and running the packaged entry points.

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
