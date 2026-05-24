# Replay State Recipe

The committed source does not include generated SQLite replay state. The replay
state for the reference scenario is reproducible from committed artifacts.

## Generation

Run:

```bash
python demo/scripts/run_code_review_demo.py
```

By default this writes:

```text
demo/state/code_review_agent.sqlite
```

The path can be overridden with `OEP_DEMO_STATE_PATH` or `--state-path`.
The runner builds the SQLite database at a temporary path and publishes the
completed file with an atomic replace, so readers do not observe an in-place
schema reset. It enables SQLite WAL mode while materializing state; if you copy
the generated state into a strictly read-only location, checkpoint and close the
database first so SQLite does not need writable `-wal` or `-shm` sidecar files.
The demo publisher assumes it owns the target state path during generation.
Adaptations that publish while other processes keep active read connections
should prefer SQLite's Backup API rather than file-level replacement or sidecar
cleanup, or serialize regeneration and replay readers with an external lock.
On Windows, an open destination file can briefly block atomic replacement; the
runner retries short `PermissionError` windows and then reports a clear publish
failure if another process keeps the database locked.

## Contents

The generated database contains the joined event, permission, trace, eval, and
finding rows for the deterministic code-review-agent scenario. Foreign keys are
enabled so replay state rows must join back to the trace and event identity.

## Verification

Run:

```bash
python demo/scripts/check_replay_state.py
```

`make verify` regenerates and checks this state as part of the repository
verification chain.

## Evidence Boundary

This recipe is the source artifact bound by the release manifest. The generated
SQLite file is reproducible runtime state and remains ignored by git.
