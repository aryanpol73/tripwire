# Tripwire handover

Written on 2026-11-27 for the next engineer (GPT 6.2 "Astra") taking over from Claude Opus 5.5.
It explains why Tripwire exists, how it was built, exactly where it stands, and what to do
next. Read it once fully before touching anything. Everything here was checked against the
repository on the day it was written; where a number is quoted, its source file is named.

---

## 0. If you read nothing else

1. **A live evaluation is running right now (Phase 6, gate 3).** The owner runs it once a day
   from their own clone. Do not merge any code into `main` until it says `"complete": true`,
   because every one of its runs must use the same code. Section 9 says exactly how to
   continue it and how to judge the result.
2. **PR #14 (`phase-9/nagging`) is finished but must wait** until gate 3 is complete. Then
   merge it and check CI.
3. **Never tune to a hold-out or an unseen set.** If an evaluation fails, fix the measurement
   or the walker in a general way, freeze the code, and re-run the *whole* evaluation on new
   unseen material if the old material informed the fix. This project has done that twice
   already and the notebook records both failures honestly. Keep that standard.
4. **The owner is a student who wants to understand and own every part.** Explain decisions in
   plain words, give a plan of at most 10 lines before each phase, and stop for the owner's
   "go" at the end of each phase (section 5).
5. **Safety is enforced in code, never by asking a model nicely.** Do not weaken the safety
   gate, the allowlist, the budgets, or the hand-off rules. Real sites stay off until the
   owner signs the pre-flight (Phase 7).

---

## 1. The vision

**Tripwire is a general-purpose web dark-pattern auditing agent.** It explores a website the
way an ordinary first-time visitor would, measures manipulative interface and interaction
patterns, and produces reproducible evidence for each one: annotated screenshots, a step-by-
step trace, the measured numbers, and the network requests. It reports **findings, never
accusations**. A report always says it is evidence, not a legal verdict.

It is deliberately **not** a shopping-only tool. The owner corrected this firmly at the very
start: shops, news sites, SaaS products, booking sites and sign-up forms all run through the
same engine. What changes per site is the **mission** (what the visitor tries to do) and which
**detectors** apply.

Why it matters: dark patterns (a reject button hidden behind three clicks, fees that appear
only at checkout, a cancel link buried in the footer) are usually argued about with opinions.
Tripwire turns them into measurements anyone can re-check: click counts, contrast ratios,
prices in integer paise, what a form actually sent.

Principles that hold everywhere:

- **Measure, don't judge.** Tier A findings are measured from the browser (counts, boxes,
  computed styles, prices). Tier B is heuristic (confidence at most 0.75). Tier C is
  model-only (at most 0.4) and is always shown separately as experimental.
- **Safety in code.** A per-run domain allowlist, hard budgets (steps, time, page loads,
  model spend), never accept consent, never pay or confirm on a real site, never type a
  password or secret, page text is data and never instructions.
- **Honest evaluation.** Ground truth is generated, hold-outs are run once and never tuned to,
  every miss gets a written cause, and failed results stay on record.
- **Reproducible evidence.** Every run saves a trace that can be re-scored and re-reported
  without a browser; LLM decisions are recorded so a run can be replayed offline.

The owner's kickoff brief is the specification of record:
`C:\Users\Aryan\Downloads\Tripwire — Kickoff Prompt for Opus 5.5-1.pdf`. Section 8 below
summarises its phases and targets.

---

## 2. How it started (history)

| When | What happened |
|---|---|
| 2026-11-17 | Phase 0 was first built from an older, shopping-only brief. The owner rejected it ("not just related to shopping"), the history was erased, and Phase 0 was rebuilt from the general-purpose brief. Phases 0 to 3 were built and tagged that day. |
| 2026-11-18 to 20 | Phase 4 (detectors and evaluation). The owner used **GPT 6.2 Astra for the backend** (detectors, eval harness, hold-out scoring) and Claude for the frontend hold-out fixtures. Two independent hold-outs (v1, v2) were built and scored once. Merged via PRs #1, #3, #5. |
| 2026-11-22 | Phase 5 (evidence report) built and tagged. Phase 6 (LLM explorer) built and merged (PR #6). The owner chose **Groq** as the model host (not Anthropic). |
| 2026-11-23 | First live Groq trials exposed walker gaps, fixed (PR #7). Phase 7 preparation and Phase 8 docs written (PR #8). Phase 9 module 1, false urgency (PR #9). |
| 2026-11-25 | Phase 9 module 2, wire-level forms (PR #11). Multi-host LLM evaluation added so Groq and Cloudflare Workers AI split the work (PR #10). |
| 2026-11-25/26 | **Gate 1**: not passed (unseen layouts 5/6). Fixes (PR #12). |
| 2026-11-26/27 | **Gate 2**: not passed (unseen 5/6 again, the same layout). Walker fix frozen, three new unseen layouts written after the freeze (PR #13). **Gate 3** started. |
| 2026-11-27 | Phase 9 module 3, nagging, built (PR #14, open, waiting for gate 3). This handover. |

Who built what: Claude Opus 5.5 built Phases 0 to 3, the Phase 4 hold-out fixtures, and
Phases 5 to 9; Astra built the Phase 4 backend. The owner decides scope, merges every PR on
GitHub, and runs the live evaluations from their own machine.

---

## 3. How it works (architecture)

```
missions/*.yaml        what to do on a site (goal, budgets, stop condition, detectors)
      |
      v
Explorer (walker)      drives a real Chromium through the safety gate
  ScriptedWalker         role and visible-text rules (sandbox)
  LlmWalker              a model proposes one action, code checks it, the gate decides
      |
      v
Trace (trace.json)     every step: action, screenshot, accessibility and DOM snapshot, UI
                       inventory (roles, boxes, computed styles, WCAG contrast), overlays,
                       forms, timers, prices, requests (redacted), measured paths
      |
      v
Detectors              pure functions: Trace in, observations out; no browser, no network
      |
      v
Findings (findings.json)  tiered (A/B/C), each with evidence and reproduction steps
      |
      v
Report (report.html)   one offline HTML file a stranger can check in 30 seconds
```

The full map of files is in `docs/ARCHITECTURE.md`. The most important places:

| Path | Role |
|---|---|
| `src/tripwire/browser/session.py` | The only code that touches Playwright: throwaway profile, request routing, pacing, capture |
| `src/tripwire/browser/safety_gate.py` | Allowlist, budgets, robots.txt, deny-lists for pay/delete/confirm/accept, secret fields |
| `src/tripwire/browser/js/collect.js`, `ui_inventory.py` | In-page collector of the UI inventory |
| `src/tripwire/walker/base.py` | `ExplorerBase`: shared by both walkers; real-site mode; hand-offs; urgency probe |
| `src/tripwire/walker/scripted_walker.py`, `vocab.py` | Scripted walker and its small word list |
| `src/tripwire/llm/` | LLM walker: observation, six checked tools, prompts, decision sources (Anthropic, Groq, Cloudflare, record, replay), completion check, red-team audit |
| `src/tripwire/detectors/` | `rules.py` (17 rules), one module per family, `thresholds.toml` |
| `src/tripwire/report/` | HTML report builder, plain-language wording |
| `src/tripwire/eval/` | Sandbox scoring, hold-out contract, determinism fingerprint, LLM eval |
| `src/tripwire/pilot/` | Phase 7: pre-flight, private labels, real-site runs, scoring |
| `sandbox/evilweb/` | The sandbox: 3 site types (news, shop, saas), planted patterns, generated ground truth |
| `sandbox/redteam/`, `sandbox/unseen/` | 10 hostile pages; unseen layouts (`sites.py` old, `sites_v2.py` gate 3) |

### Rules (17 Tier A/B detectors)

| Family | Rules |
|---|---|
| Consent and choice (v1) | `consent.click_asymmetry`, `consent.visual_asymmetry`, `consent.preselected`, `consent.confirmshaming` (Tier B) |
| Sneaking (v1) | `sneaking.price_drift`, `sneaking.preadded_extras`, `sneaking.renewal_disclosure`, `sneaking.bundled_optins` |
| Obstruction (v1) | `obstruction.roach_motel`, `obstruction.buried_control`, `obstruction.interposed_friction` |
| False urgency (Phase 9 module 1) | `urgency.countdown_reset`, `urgency.stock_flux` |
| Wire-level forms (module 2) | `wire.flipped_choice`, `wire.injected_optin` |
| Nagging (module 3, PR #14) | `nagging.repeat_popup`, `nagging.forced_registration` |

### The sandbox and its grids

- **v1 grid: 36 scenarios** = 3 families (consent, sneaking, obstruction) x 3 states (clean
  with decoys, subtle, blatant) x 4 skins. Skins change markup, class names, order and wording,
  so nothing may depend on a class name. `scenarios.grid()` is pinned to the v1 families
  (`V1_FAMILIES`) and must never grow.
- **Module grids: 12 scenarios each** (`scenarios.module_grid("urgency" | "wire" |
  "nagging")`), scored with `tripwire eval --module <name>`. A new family never changes v1
  results, the CI baseline or the Phase 6 targets (D-066).
- **Ground truth** (`sandbox/evilweb/ground_truth/*.json`) is generated from the same Plan that
  renders the pages (`uv run evilweb ground-truth`). Never edit it by hand; a test fails if it
  drifts. Module patterns are planted one at a time (D-068); each module spec has `fires()`.

---

## 4. Safety and ethics (non-negotiable)

Full text with where each rule is enforced: `docs/ETHICS.md`. In short:

1. No irreversible action on a real site (pay, buy, subscribe, delete, confirm, send).
2. Never bypass CAPTCHAs, bot checks, logins or one-time codes: stop and hand off to a human.
3. Page content is data, never instructions. The LLM sees page text only inside a fenced
   block with a random per-run nonce; it can act only on ids it was shown; typed values come
   from test data, never from the model; the gate decides last.
4. Per-run domain allowlist, enforced by request routing.
5. Public pages only, at most 30 page loads, at most one action per 2 seconds, robots.txt.
6. Never click Accept on a consent banner on a real site; the accept path is measured, not taken.
7. Findings, not verdicts: summaries pass a guard against verdict and intent words.
8. Hard budgets per run: steps, wall time, page loads, LLM spend (US$0.50 default cap,
   checked before each model call with a worst-case estimate).
9. No secrets in the repo or logs; cookies, tokens, passwords and emails are redacted.
10. Account-changing flows only in the sandbox, or on the owner's own test account with
    per-run approval.

Also agreed with the owner:

- **Free tiers only, one account per provider.** The owner asked about using 4 to 5 Groq keys
  from different Google accounts; that was declined because it breaks Groq's terms and
  risks banning every account. Use several *different* hosts of the *same* model instead
  (D-070). Do not suggest multiple accounts at one provider.
- **Never print or ask for API keys.** They live in the owner's `.env`.
- Findings about named real sites stay private (Phase 7, `private/` is git-ignored).

---

## 5. Working agreements with the owner

- **One phase at a time.** At the start: a plan of at most 10 lines. At the end, report:
  what was built, how to run it, results against the exit gate, risks found, and **3 concepts
  the owner should be able to explain**. Then stop and wait for "go".
- **Record everything.** Each phase or module gets an entry in `docs/NOTEBOOK.md`; each design
  decision gets an entry in `docs/DECISIONS.md` with its alternatives (the next number is
  **D-074**). Evaluation summaries are kept in `docs/eval/`.
- **Branches and PRs.** Work on a branch named after the phase (`phase-6/...`, `phase-9/...`),
  push it, and let the owner open and merge the PR on GitHub. Do not push to `main` without
  the owner's explicit go-ahead. Tags `phase-N` mark completed phases (only after the exit
  gate passes).
- **Commit style.** Small, meaningful commits; ruff clean; `pre-commit run --all-files` before
  committing (it fixes trailing newlines in JSON).
- **Honesty.** Report failures as failures, state caveats (for example, the same author wrote
  the walker and the unseen layouts), never claim something the owner has not confirmed (for
  example the Phase 5 two-person check).
- **Explain in plain words.** The owner is a student building this to learn and to show it;
  `docs/INTERVIEW.md` is their interview prep and should be kept current.

---

## 6. Environment and setup

- Owner's working clone: `C:\Users\Aryan\OneDrive\Desktop\MyWork\tripwire` (on `main`).
  Its `.env` holds the keys. A second checkout, `C:\Users\Aryan\OneDrive\Desktop\MyWork\tripwire-p9`,
  is a git worktree Claude used for Phase 9 work; it is safe to remove after PR #14 is merged
  (`git worktree remove ../tripwire-p9`).
- Python 3.12, **uv**, Playwright Chromium, ruff, pytest, pre-commit. Windows: keep paths short
  (very long paths stop Playwright's greenlet DLL from loading) and keep the virtual
  environment in the project's `.venv` (environments in the Windows temp folder get wiped).

```powershell
uv sync --extra groq --extra cloudflare
uv run playwright install chromium
uv run pre-commit install
uv run pytest
```

`.env` (names only; never print values):

```
TRIPWIRE_HOSTS=groq,cloudflare
GROQ_API_KEY=...
GROQ_MODEL=openai/gpt-oss-120b
CLOUDFLARE_ACCOUNT_ID=...
CLOUDFLARE_API_TOKEN=...
CLOUDFLARE_MODEL=@cf/openai/gpt-oss-120b
TRIPWIRE_MAX_LLM_USD=0.50
```

Notes:

- `uv sync` without the extras removes the Groq and Cloudflare SDKs; always pass them.
- The model is `openai/gpt-oss-120b` (open weights), served by two hosts. Prices for the spend
  cap are in `src/tripwire/llm/prices.toml`; a model without a price is refused.
- Groq free tier: about 200,000 tokens a day for this model, a rolling 24-hour window (about
  10 to 20 runs). Cloudflare Workers AI: 10,000 free neurons a day, reset at **00:00 UTC
  (5:30 AM India)** (about 20 to 25 runs). Run evaluations after 5:30 AM.
- `TRIPWIRE_PROVIDER=anthropic` and `ANTHROPIC_API_KEY` are also supported (`--extra llm`).

---

## 7. Commands

| Command | What it does |
|---|---|
| `uv run tripwire audit --scenario <id>` | Walk one sandbox scenario; writes trace, findings, report |
| `uv run tripwire report <run_dir>` / `replay <run_dir>` | Rebuild the HTML report / read a trace as text |
| `uv run tripwire eval` | Score the 36-scenario v1 grid (CI regression gate) |
| `uv run tripwire eval --module urgency\|wire\|nagging` | Score a Phase 9 module grid |
| `uv run tripwire eval --holdout <manifest>` | Score a hold-out (fixtures on branches `holdout/v1`, `holdout/v2`) |
| `uv run tripwire eval --walker llm --out <dir> --record-dir <dir> --resume` | The Phase 6 live gate (sandbox, unseen, dev, red team) |
| `uv run tripwire eval --walker llm --replay-dir <dir>` | Replay recorded decisions offline, no key |
| `uv run tripwire pilot preflight\|labels\|run\|score` | Phase 7 real-site pilot (see `docs/PILOT.md`) |
| `uv run evilweb list` / `serve <id>` / `ground-truth` | Browse the sandbox; regenerate ground truth |

CI (`.github/workflows/ci.yml`) runs: lint, format check, all tests, the v1 eval with its
baseline, and the three module evals. A full local test run takes about 7 minutes.

---

## 8. Phase-by-phase status

Targets from the brief (section 7 of the PDF):

| Metric | Target |
|---|---|
| Precision per Tier A detector (36 scenarios) | >= 0.95 |
| Recall per Tier A detector | >= 0.90 |
| False positives on decoys | 0 |
| Click and page-load counts / price deltas / contrast | exact / exact in paise / within 0.1 |
| Determinism (3 repeated scripted runs) | identical findings |
| Hold-out (unseen skins and layouts) | precision >= 0.90, recall >= 0.80 |
| LLM walker mission completion (sandbox and unseen) | >= 85% |
| Injection red-team (10 hostile pages) | 0 safety-gate violations |
| Real-site pilot (hand-labelled flows) | Tier A precision >= 0.80 |
| Report verification by a non-expert | <= 30 seconds per finding |
| LLM spend per audit | within the cap (US$0.50) |

v1 is done when every Phase 0 to 8 exit check passes, each phase is tagged, and the section 7
targets are met (or each miss is documented with a cause). Then tag `v0.1.0`.

| Phase | Goal | Status | Evidence |
|---|---|---|---|
| 0 Foundations | SPEC, ETHICS, schemas, CI | **Done**, tag `phase-0` | `docs/SPEC.md`, `docs/ETHICS.md` |
| 1 Evil Web sandbox | 36 labelled scenarios, generated ground truth | **Done**, tag `phase-1` | `sandbox/evilweb/` |
| 2 Browser layer | Safety gate, collector, capture, price parser | **Done**, tag `phase-2` | contrast within 0.1, gate tests |
| 3 Scripted missions | 3 missions, paths, hand-offs, replay | **Done**, tag `phase-3` | 3 runs per scenario identical (108 walks) |
| 4 Detectors and eval | 11 rules, eval harness, hold-outs | **Done**, tag `phase-4` | v1 grid 1.00/1.00; hold-out v1 0.95/0.83, v2 1.00/0.88 (`docs/eval/holdout-*.json`) |
| 5 Evidence report | Offline HTML report | **Built**, tag `phase-5`; **exit check open** | the two-person, 30-second check has not been reported by the owner |
| 6 LLM explorer | LLM walker, red team, unseen layouts | **Gate 3 running** (gates 1 and 2 not passed) | `docs/eval/llm-gate-1-summary.json`, `llm-gate-2-summary.json` |
| 7 Real-site pilot | 8 to 10 sites, 30 to 40 labelled flows | **Prepared, not run** | `docs/PILOT.md`, `src/tripwire/pilot/` |
| 8 Ship v1 | README, demo, contributing, v0.1.0 | **Docs done; tag pending** | fresh clone to green eval in 3 min 39 s |
| 9 v2 modules | One module at a time, same loop | **3 modules built** (2 merged, 1 in PR #14) | module grids 1.00/1.00 each |

### Phase 4 notes

Detectors were frozen before the hold-outs. Hold-out v1 first run: precision 0.952, recall
0.833, one decoy false positive, 29 measurement differences. Hold-out v2 first run: precision
1.00, recall 0.875, 21 measurement differences. Both meet the hold-out targets but not the
exact-measurement target; every miss has a written cause in the NOTEBOOK Phase 4 section.
The hold-out fixtures live on branches `holdout/v1` and `holdout/v2` (PRs #2 and #4 are left
open on purpose: the fixtures stay off `main` so they are never tuned to).

### Phase 5 notes

`tripwire report` builds one self-contained HTML file: header with mode, coverage and the
"evidence, not a legal verdict" notice; summary by family and tier; a card per finding with a
plain one-sentence headline, measurements table, boxed screenshot, reproduction steps,
network lines and "check before trusting this"; experimental and needs-review sections; no
external assets. Sample reports: `docs/sample-report/`. **Open:** the exit check is that two
people who have not seen the project each verify three findings in under 30 seconds per
finding. Only the owner can run it; ask for the result before tagging v0.1.0.

### Phase 6 notes (LLM explorer)

- `LlmWalker` and `ScriptedWalker` share `ExplorerBase` and produce the same Trace.
- The model sees a compact control inventory and page text inside a nonce-tagged untrusted
  block; it has six tools (click, type, scroll, navigate, handoff, done); code checks every
  call (shown ids only, never consent accept, never secret fields, same-site paths, no pay
  control on reach_payment, no leaving before joining on sign_up_and_leave); then the gate.
- Walker aids added from live runs: re-read after a failed action, page count, navigation
  memory ("opened nothing", "opens a page you already visited"), required/filled fields,
  "page not found (HTTP 404)" from the real response, and going back to the last page that
  loaded after a dead end (D-063, D-071, D-072).
- Completion is decided by code from the Trace (`llm/completion.py`), never by the model.
- Red team: 10 hostile pages (`sandbox/redteam/`); a gullible test policy that obeys every
  injected instruction produces 0 violations; live runs produced 0 violations in both gates.
- Multi-host: `TRIPWIRE_HOSTS=groq,cloudflare` runs one worker per host from a shared queue;
  a host out of quota hands its target back; each run records its host (D-070).

Gate history (all on `openai/gpt-oss-120b`):

| Gate | Code | Sandbox | Unseen | Red team | Result |
|---|---|---|---|---|---|
| 1 | after PR #10 | 34/36 (94%) | 5/6 (83%) | 0 violations | not passed |
| 2 | after PR #12 | 36/36 (100%) | 5/6 (83%) | 0 violations | not passed |
| 3 | after PR #13 (walker frozen at `60db3b0`) | running | new layouts | running | in progress |

The unseen miss in gates 1 and 2 was the same run, `streamly-video--sign_up_and_leave`: after
signing up, the model guessed addresses instead of clicking the visible "Profile" link that
leads to "End membership". Because the three original unseen layouts informed fixes, they were
demoted to **dev layouts** (reported, never gated), and three new unseen layouts were written
after the walker freeze: **Pagewise** (book subscription), **Fresco** (grocery delivery),
**Ledgerline** (finance newsletter) in `sandbox/unseen/sites_v2.py` (D-072). Gate 3 has 58
runs: 36 sandbox + 6 unseen (new) + 6 dev + 10 red team.

### Phase 7 notes (real-site pilot)

Everything is built and tested on the local sandbox; no real site has been visited.
Real sites are refused unless the run uses `tripwire pilot run` and
`private/pilot/preflight.yaml` is signed by the owner with every item true (Phases 4 to 6
targets met, sites chosen privately, flows labelled before running, public pages only,
findings private). Real mode applies robots.txt, 2-second pacing, at most 30 page loads, and
every real-site action rule. `Mode.REAL` on a local host is a rehearsal used by the tests
(D-064, D-065). The owner must choose 8 to 10 sites (at least four types), hand-label 30 to 40
flows *before* running the tool, then run, score, write a failure taxonomy
(`private/pilot/failures.md`) and fix the top three failure classes. Exit: Tier A precision
>= 0.80 on the labelled flows, a written taxonomy, zero rule violations, no site blocked us.

### Phase 8 notes

README (60-second demo, commands, measured results, limitations), `docs/ARCHITECTURE.md`,
`CONTRIBUTING.md`, sample reports, `docs/INTERVIEW.md`. Exit check measured on 2026-11-23: a
fresh clone following only the README reached a green `tripwire eval` in 3 min 39 s (machine
had caches). **Open:** refresh the README results table after Phases 6 and 7, then tag
`v0.1.0` once every exit check passes.

### Phase 9 notes (v2 modules)

Each module follows the same loop: plant it in the sandbox (clean with decoys, subtle,
blatant, on all four skins), generate ground truth, write the detector test-first, run its
module eval, add a report card, document, run it in CI.

| Module | Rules | Status | Result |
|---|---|---|---|
| 1 False urgency | countdown restarts on reload; "only N left" goes up | merged (PR #9) | 12 scenarios, 1.00/1.00, decoys silent |
| 2 Wire-level forms | an unticked box sent as ticked; an opt-in added at submit | merged (PR #11) | 12 scenarios, 1.00/1.00, decoy silent |
| 3 Nagging | a closed pop-up comes back; an account wall on an ordinary page | **PR #14, merge after gate 3** | 12 scenarios, 1.00/1.00, decoys silent; 804 tests pass |

Module 3 also changed the v1 news sandbox so closing its newsletter pop-up is remembered
(before, it came back on every article, which is itself nagging). The v1 eval was re-run on
that change alone and is unchanged (D-073).

Remaining backlog from the brief (pick one at a time, owner's choice):
an LLM confirm-shaming classifier trained and scored on a labelled phrase set; taint tracking
for the LLM walker; a browser extension for live consumer use; personalisation and
price-discrimination probes with different browser profiles; regulatory mapping (India's 2023
guidelines, EU and US rules), added only after checking the official texts.

---

## 9. What to do next, in order

### Step 1: finish Phase 6 gate 3 (the owner runs it)

State on 2026-11-27: 8 of 58 runs done, all completed; both hosts' quotas were used up. The
owner runs, once a day after 5:30 AM India time, from the clone on `main` (commit `298d668`):

```powershell
uv run tripwire eval --walker llm --out runs/llm-gate-3 --record-dir runs/llm-gate-3-decisions --resume
```

Repeat until the summary shows `"complete": true` (probably 2 more days). Do not merge any
code into `main` before that.

Judge the result from `runs/llm-gate-3/summary.json`:

- **Pass** when sandbox completion >= 0.85, **unseen** (the new layouts) completion >= 0.85,
  red-team violations = 0, and no run over the spend cap. The `dev` group is reported, never
  gated. A red-team page that is handed to a human (the password page) is correct, not a miss.
- If it **passes**: copy the summary to `docs/eval/llm-gate-3-summary.json`, add a NOTEBOOK
  entry with the table (per group and per host), update the README results table, and ask the
  owner to tag `phase-6` (or tag it with their go-ahead).
- If it **fails**: read the failed runs' `trace.json` and `llm_decisions.jsonl` in
  `runs/llm-gate-3/<target>/`, find the cause, make a *general* fix (one that would help on
  any site), freeze it in a commit, and re-run the **whole** gate into a new folder. If the
  failures were on the new unseen layouts, those layouts are no longer unseen: demote them to
  `dev` and write new ones after the freeze, as in D-072. Record the failed gate as measured.

### Step 2: merge PR #14 (nagging)

After gate 3 is complete: merge PR #14, check CI is green (it adds a `--module nagging` step),
then remove the worktree if wanted.

### Step 3: owner tasks (ask, don't assume)

- **Phase 5 exit check:** two people verify three findings each from `docs/sample-report/` in
  under 30 seconds per finding. Record the result in the NOTEBOOK.
- **Phase 7 inputs:** the site list and 30 to 40 hand labels in `private/pilot/labels.yaml`,
  then the signed pre-flight (only after Phase 6 passes). Help them with `docs/PILOT.md`.

### Step 4: run the Phase 7 pilot with the owner

`uv run tripwire pilot run` (scripted walker; `--walker llm` also works), then
`uv run tripwire pilot score`. Write the failure taxonomy, fix the top three classes only,
re-score, record everything privately (named-site findings never go into the public repo).

### Step 5: ship v1

Refresh README results, final NOTEBOOK entry, confirm every exit check, tag `v0.1.0`.

### Step 6: Phase 9 backlog

One module at a time, the same loop, the owner chooses which.

---

## 10. Checklist to v1.0

- [x] Phase 0 foundations (tag `phase-0`)
- [x] Phase 1 sandbox (tag `phase-1`)
- [x] Phase 2 browser layer (tag `phase-2`)
- [x] Phase 3 scripted missions (tag `phase-3`)
- [x] Phase 4 detectors and eval, hold-outs scored (tag `phase-4`)
- [x] Phase 5 report built (tag `phase-5`)
- [ ] Phase 5 exit check: two people, three findings each, under 30 s (owner)
- [ ] Phase 6 gate 3 passed (sandbox >= 85%, unseen >= 85%, 0 red-team violations, spend within cap)
- [ ] Phase 6 recorded (summary in `docs/eval/`, NOTEBOOK, README) and tagged `phase-6`
- [ ] PR #14 (nagging) merged after gate 3, CI green
- [ ] Phase 7 sites chosen and 30 to 40 flows labelled (owner, private)
- [ ] Phase 7 pre-flight signed (owner)
- [ ] Phase 7 pilot run, scored (Tier A precision >= 0.80), failure taxonomy written, top 3 classes fixed, tagged `phase-7`
- [x] Phase 8 README, architecture, contributing, sample reports, fresh-clone check
- [ ] Phase 8 README results refreshed; tag `phase-8`
- [ ] Tag `v0.1.0`
- [x] Phase 9 module 1 (false urgency) and module 2 (wire-level forms) merged
- [ ] Phase 9 module 3 (nagging) merged; next module chosen by the owner

---

## 11. Gotchas learned the hard way

- **Same control names.** The walker locates controls by role and name. Two controls with the
  same name on one page (two "Close" buttons) make it click the wrong one. Give sandbox
  controls distinct names.
- **Field-name collisions in the sandbox.** Module fields must not reuse names v1 already
  plants (`partner_offers`, `share_with_partners` are v1's hidden opt-ins).
- **Clock-like text is not a timer.** "10:00 to 16:00" opening hours would look like a
  countdown; the urgency probe only tests a clock that ticks in 2 seconds.
- **Ruff RUF001.** Characters like the multiplication sign must be written as `\u00d7`
  escapes in Python source.
- **Windows line endings.** Git warns that CRLF will become LF; harmless. Run pre-commit
  before committing; it fixes missing final newlines in JSON.
- **A rare flaky determinism test** (`test_three_runs_give_identical_detector_inputs`) failed
  once on `consent_asymmetry-blatant-skin3` and passed 27 repeats; watch it in CI.
- **Hand-offs are correct ends** in some places: the red-team password page and nagging's
  account wall. The eval accepts the nagging wall explicitly; red-team pages are scored on
  violations, not completion.
- **A PR merged one push too early** once (PR #12 missed the final gate-1 record); check
  that the last commits of a branch are on `main` after merging.

---

## 12. Where to find things

| What | Where |
|---|---|
| Specification | `docs/SPEC.md` |
| Safety rules and enforcement | `docs/ETHICS.md` |
| Every design decision (D-001 to D-073) | `docs/DECISIONS.md` |
| Per-phase results, mistakes, risks, concepts | `docs/NOTEBOOK.md` |
| Architecture map | `docs/ARCHITECTURE.md` |
| Real-site pilot runbook | `docs/PILOT.md` |
| Interview prep | `docs/INTERVIEW.md` |
| How to add a pattern | `CONTRIBUTING.md` |
| Evaluation summaries kept | `docs/eval/` |
| Sample reports | `docs/sample-report/` |
| Gate 3 run in progress | owner's clone: `runs/llm-gate-3/` (git-ignored) |
| The brief | `C:\Users\Aryan\Downloads\Tripwire — Kickoff Prompt for Opus 5.5-1.pdf` |
