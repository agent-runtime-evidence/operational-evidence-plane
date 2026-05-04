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
