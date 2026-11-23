# Contributing

Thank you for helping. Tripwire measures manipulative design and reports evidence, never
accusations. Every change keeps that true, and keeps the [ETHICS](docs/ETHICS.md) rules
enforced in code.

## Set up

```bash
uv sync
uv run playwright install chromium
uv run pre-commit install
uv run pytest
```

On Windows keep the checkout path short (for example `C:\code\tripwire`).

## The loop for a new pattern

Every pattern goes through the same five steps, in this order. A pull request that skips one
is not ready.

### 1. Plant it in the sandbox

Patterns live in `sandbox/evilweb/patterns/` (`consent.py`, `sneaking.py`,
`obstruction.py`). Each surface has a spec with a `clean` (including a decoy that looks
similar but is fair), `subtle` and `blatant` state, and it must render on all four skins
(`sandbox/evilweb/skins.py`). Skins change markup, order and wording, so never let a
detector depend on a class name. Wire the spec into the scenario's `Plan`
(`sandbox/evilweb/plan.py`), which both the web app and the ground truth read.

### 2. Generate the ground truth

```bash
uv run evilweb ground-truth
```

This writes `sandbox/evilweb/ground_truth/*.json` from the Plan: which rules must fire and
the exact numbers (clicks, page loads, minor currency units, contrast). Commit the files; a
test fails if they drift from the Plan. Never edit them by hand.

### 3. Write the detector, test first

- Add the rule to `src/tripwire/detectors/rules.py`: id, family, tier, and the plain
  question it answers.
- Write unit tests in `tests/unit/test_detectors.py` on fixture traces: one violating, one
  clean, one decoy. Then implement it in `src/tripwire/detectors/<family>.py` as a pure
  function of the Trace. Put thresholds in `thresholds.toml`, never in code.
- Tier A must be measured from the trace (counts, boxes, computed styles, prices). If it needs
  judgement it is Tier B (confidence at most 0.75); model-only is Tier C (at most 0.4).
- Summaries are one plain sentence with no verdict or intent words; the schema rejects them.

### 4. Run the eval

```bash
uv run tripwire eval
```

Precision and recall must hold the targets in the [SPEC](docs/SPEC.md), with zero false
positives on decoys and exact counts. CI fails on a drop of more than two points. If the
hold-out misses, improve the measurement; never tune a threshold to the hold-out.

### 5. Give it a report card

Add its title, one-sentence headline and metric labels to `src/tripwire/report/plain.py`,
and, if the evidence is a control on screen, a box mapping in `src/tripwire/report/builder.py`.
Build a report from a sandbox run and check a stranger could verify it in 30 seconds.

## Safety rules for any change

- The gate (`src/tripwire/browser/safety_gate.py`) is the only place that decides whether an
  action may happen. Do not add a way around it, and do not let page content or a model change
  it.
- No real-site runs in tests or CI. Real sites need the signed pre-flight (`docs/PILOT.md`).
- Never commit traces, HAR files, `.env`, or anything under `private/`.
- Record every design decision with its alternatives in `docs/DECISIONS.md`.

## Style

`uv run ruff check .` and `uv run ruff format .` must pass. Write comments that explain why,
in plain words.
