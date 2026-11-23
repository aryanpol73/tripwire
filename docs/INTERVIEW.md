# Interview prep: Tripwire

## The 30-second pitch

Tripwire is an agent that audits websites for manipulative design. It walks a site like a
first-time visitor, measures what that visitor meets (how many clicks it takes to reject
cookies compared with accepting, charges that appear only at checkout, a cancel link hidden in
the footer) and writes an offline evidence report a stranger can check in 30 seconds. It
reports measurements, never accusations, and its safety rules are enforced in code, not in a
prompt.

## How it works, in one breath

A YAML mission drives a walker through a real browser. Every action goes through a safety
gate. Each step is captured into a Trace: screenshot, accessibility tree, computed styles,
contrast, overlays, forms, prices, requests. Pure-function detectors read the Trace and emit
tiered findings. A report turns them into plain sentences with boxed screenshots. See
[ARCHITECTURE](ARCHITECTURE.md).

## Numbers you can quote (all measured)

- 36 sandbox scenarios (3 families x 3 states x 4 skins): Tier A precision and recall 1.00,
  zero false positives on decoys, deterministic over three runs.
- Two independent hold-outs, run once with no tuning: precision 0.95 / recall 0.83, and
  1.00 / 0.88. The brief's target is at least 0.90 / 0.80.
- Red-team: 10 hostile pages, 0 violations even with a test policy that obeys every injected
  instruction.
- LLM spend capped at US$0.50 per audit, enforced before each model call; live runs on
  Groq cost about US$0.004 each.

## Decisions worth explaining

1. **Safety in code, not in the prompt** (D-054). The model proposes; code checks the
   proposal against what the model was shown; then the gate decides. Injection can change
   the proposal, never the checks.
2. **Tiers** (A measured, B heuristic, C model-only, with confidence caps). A number from the
   browser is stronger evidence than a model's opinion, and the report shows the difference.
3. **A sandbox with generated ground truth** (Phase 1). The same Plan renders the page and
   writes the expected answer, so they cannot drift apart; four skins stop detectors from
   keying on class names.
4. **Hold-outs run once, never tuned** (D-046). If they miss, improve the measurement, not
   the threshold.
5. **Record and replay** (D-061). Logging every model decision with its request hash turns a
   non-deterministic run into a repeatable test.
6. **Untrusted blocks with a random nonce** (D-055). Page text cannot forge the end of the
   fence, because it cannot know the tag.
7. **Pre-registration for the pilot** (D-065). Label real flows before running the tool, so
   its output cannot shape the labels.

## Mistakes and what they taught

- **Building the wrong product first.** Phase 0 started as a shopping-only tool; the owner
  wanted a general auditor. Lesson: restate scope in one sentence and confirm it before code.
- **The gate's evidence was wrong.** A blocked off-site navigation was logged as not blocked,
  because the browser's request event fires before the route handler. Found by the red-team
  auditor. Lesson: test the evidence, not only the behaviour.
- **A guessable nonce.** It came from the run id, which made replays diverge and could be
  predicted. Now random per run and stored in the recording.
- **"PIN code" refused as a secret.** In India it is a postal code. Lesson: keep one
  definition of a rule (the gate's) and reuse it.
- **Free-tier quota.** 200,000 tokens a day stopped the first live eval after 13 runs; the
  eval now stops cleanly and resumes.
- **Optimistic estimates.** Trimming prompts saved about 10% of tokens, not the half
  estimated. Measure before promising.

## Likely questions

**How do you know a finding is real?** Tier A findings carry the measured numbers, the boxed
screenshot, reproduction steps and the requests. Detectors are scored against ground truth
on 36 scenarios and two hold-outs, and decoys (fair designs that look similar) must stay
silent.

**What stops prompt injection?** The model never sees the gate, the allowlist or the budgets,
cannot choose typed text, and can act only on ids it was shown. Every proposal is checked in
code and then by the gate. The red-team set tests it; a gullible test policy causes zero
violations.

**Why not just ask a model "is this a dark pattern"?** It is not reproducible, not
measurable, and easy to argue with. A click count or a contrast ratio is. Model judgement is
kept to Tier C and labelled experimental.

**What would break on real sites?** Consent managers in cross-site iframes, anti-bot walls,
pages that change per visit, wording outside the vocabulary. The Phase 7 pilot measures these
and writes a failure taxonomy before fixing the top three.

**What would you do next?** Run the real-site pilot; then Phase 9 modules one at a time:
false urgency (timers that reset), nagging, wire-level hidden fields, and taint tracking for
the LLM walker.
