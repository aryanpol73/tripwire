# Engineering notebook

Per phase: what was built, why, what broke, the trade-offs, and interview-style questions
with answers.

---

## Phase 0 — Setup and spec

### Mission, in five lines
1. Tripwire is a web auditor that visits any kind of site (shop, news, SaaS, booking, sign-up) and acts like an ordinary user on a short, named mission.
2. It records everything it measured (clicks, page loads, computed styles, default states, prices, network requests) into a self-contained Trace.
3. Pure, browser-free detectors read the Trace and report measured asymmetries in three families: consent asymmetry, sneaking and obstruction.
4. Every finding carries numbers, screenshots and reproduction steps a stranger can check in 30 seconds, and never claims illegality or intent.
5. We prove precision and recall on a labelled multi-site sandbox (with a hold-out) before running carefully on a handful of real sites.

### Top 5 risks and assumptions
1. **Consent banners often come from third-party scripts or iframes** (consent-management
   platforms on another domain). If the allowlist blocked every off-domain request, the banner
   would never render and Tripwire would report "no banner". *Assumption:* the allowlist
   restricts **navigation** (where the browser goes), while sub-resources load normally and are
   logged. Measuring inside cross-origin iframes is a known Phase 2/7 difficulty.
2. **Computed-style measurements can look precise and be wrong.** Gradients, background images,
   stacked opacity, shadow DOM and `::before` text make "the" background colour ambiguous. A
   wrong contrast number presented at Tier A confidence is worse than none. *Mitigation:*
   `contrast_ratio` is nullable, and a null means the visual rule does not fire.
3. **Small samples.** 36 scenarios give each family 8 non-clean scenarios. If each scenario
   plants only one of a family's 3–4 rules, a rule gets 2–3 positives, and one miss drops
   recall to 0.67. *Mitigation:* proposal P1 below.
4. **We grade our own homework.** We build both Evil Web and the detectors, so sandbox scores
   mostly show the code matches our spec. The hold-out set and the Phase 7 hand labels are the
   real tests.
5. **Real-site variability.** Banners differ by region (many Indian sites show none),
   pages change per visit, and anti-bot walls end runs early. *Assumption:* Phase 7 reports
   coverage honestly; "no banner shown" is a valid measured outcome, not a failure.

### Proposed changes to the plan
- **P1: every non-clean scenario plants every Tier A rule of its family**, at a near-threshold
  value for `subtle` and an obvious value for `blatant`. That gives each Tier A rule 8
  positives and 4 clean negatives in the 36 scenarios, instead of 2–3 positives. It keeps the
  36-scenario grid unchanged.
- **P2: contract additions** (DECISIONS D-004). Each one is required by a rule, a decoy or an
  ethics rule already in the brief.
- **P3: confidence caps per tier** (D-008), so Tier C findings can never look as certain as
  Tier A ones.
- **P4: "allowlist" means navigation, not every request** (risk 1). This matches the brief's
  wording ("block navigation elsewhere"), but it should be stated explicitly because it changes
  what the gate blocks.
- **P5: define "advertised total" for price drift precisely** as the lowest total (or sum of
  mandatory item lines) shown on any step before the last. This avoids comparing against a
  product's crossed-out MRP.

### What was built
- uv project, ruff, pytest, pre-commit (ruff via `uv run`, plus YAML/JSON/private-key checks),
  GitHub Actions CI (lint, format check, tests).
- Folder layout from the brief: `missions/`, `src/tripwire/{schemas,browser,walker,detectors,
  report,eval}`, `sandbox/evilweb/{shop,news,saas}`, `tests/{unit,fixtures,e2e}`.
- `src/tripwire/schemas/`: `Trace` and `Finding` / `FindingSet` pydantic models with
  cross-reference validation, plus validated read/write helpers.
- Six hand-written fixture traces (violating and clean for each family) and one example
  finding. A test checks that their click and page-load counts actually add up.
- `tripwire --version` CLI stub.
- Docs: SPEC, ETHICS (with responsible disclosure), DECISIONS, this notebook.

### What broke
- **The first Phase 0 was built for the wrong product.** It followed an earlier brief that
  framed Tripwire as a shopping-checkout tool. That history was erased and Phase 0 was rebuilt
  from the general-purpose brief. Lesson: confirm the product's scope before writing contracts,
  because everything else is built on them.
- **Hand-writing fixtures is error-prone.** Counting clicks and page loads by hand in a
  10-step trace is easy to get wrong. That is why `test_fixture_numbers_add_up` exists.

### Trade-offs
- **Strict schemas** (`extra="forbid"`, strict ints, exact version, cross-reference checks)
  make early iteration slower, because every field change means updating fixtures. In return,
  a walker/detector mismatch fails loudly instead of producing quiet wrong numbers.
- **Nested, typed sub-models** (overlays, forms, paths) instead of free-form dicts: more code
  now, but detectors get autocompletion and validation, and the JSON is self-documenting.

### Exit check status
- `uv run pytest`: green locally (run it to see the current count).
- CI: runs on push.
- "I can explain the pipeline from SPEC.md alone": **waiting for your review.**

### Interview questions
**Q: Why separate the Walker from the Detectors with a saved Trace?**
A: Observing needs a browser, so it is slow and flaky; judging is pure logic. A saved Trace
lets detectors run in milliseconds in unit tests, be re-run offline after a rule change, and
be audited by someone who never runs a browser.

**Q: What is a Tier A detector, and why do only Tier A rules count toward the headline?**
A: Tier A decides by deterministic measurement (click counts, computed contrast, default
states, price ledgers). Two people running it get the same answer. Tier B and C involve
heuristics or LLM judgement, which can be useful but cannot be verified the same way, so they
are reported separately and capped in confidence.

**Q: Why is money stored as integer minor units?**
A: Binary floats cannot represent most decimal fractions exactly (`0.29 * 100` is
`28.999999999999996`), so sums drift and "exact to the paisa" comparisons fail at random.
Integers in the smallest unit are exact.

**Q: How do you stop a finding from becoming an accusation?**
A: In code. The Finding schema rejects verdict and intent words, requires measured values for
Tier A, requires reproduction steps and "what to check" notes, caps confidence by tier, and
marks every taxonomy label as informational.

**Q: What is a decoy, and why does every rule need one?**
A: A legitimate design that looks like the pattern, such as a locked-on "strictly necessary"
toggle or a single confirm dialog when cancelling. Decoys test precision: a rule that fires on
them would accuse honest sites, which is the most damaging error for this tool.

---

## Phase 1 — Evil Web sandbox

### Plan (as given at the start)
Rule catalog and ground-truth schema; the 36-scenario grid; four skins; one pattern module per
family; three FastAPI + Jinja2 sites; generated ground truth; `evilweb list / serve`; tests that
render every page offline; smoke notes; tag `phase-1`.

### What was built
- `tripwire/detectors/rules.py`: the 11 v1 rule ids, each with family, tier and the question it
  answers.
- `tripwire/schemas/ground_truth.py`: `GroundTruth` with per-rule expectations (should fire, and
  exact metrics) and decoys. It enforces the planting rule (P1): a non-clean scenario plants
  every applicable Tier A rule of its family; a clean one plants none; other families never fire.
- `tripwire/browser/color.py`: WCAG contrast for opaque colours, tested against reference pairs.
- `sandbox/evilweb/`: grid, skins, pattern specs, plan, app factory, shop/news/saas sites, a
  shared leave flow, generated `ground_truth/*.json` (36 files), and the `evilweb` CLI.
- Tests: every page of all 36 scenarios renders with no external resource; banners render the
  planned layers; shop totals, saas review totals and leave-flow endings match ground truth;
  ground truth is current. 243 sandbox tests, all green.

### Ground-truth coverage (measured, not estimated)

| Rule | Tier | should fire | should stay silent |
|---|---|---|---|
| consent.click_asymmetry / visual_asymmetry / preselected | A | 8 each | 22 each |
| consent.confirmshaming | B | 4 | 26 |
| sneaking.price_drift / preadded_extras / bundled_optins | A | 8 each | 16 each |
| sneaking.renewal_disclosure | A | 4 | 14 |
| obstruction.roach_motel / buried_control / interposed_friction | A | 8 each | 16 each |

Scenarios per site type: news 12, saas 18, shop 6.

### What broke (and was fixed)
- **Cookies ignore ports.** A "reject" made on one scenario's server (port 8101) hid the banner
  on another (port 8102). Real walker runs use a fresh browser profile, so they were never
  affected, but hand-testing was. Fix: the banner needs both the cookie and the server's own
  record (D-021). Regression test added.
- **Escaped CSS silently dropped the skin fonts.** Jinja auto-escaping turned `'` into `&#39;`
  inside `<style>`, where browsers do not decode entities, so every font rule with a quoted font
  name was invalid. Unit tests passed because they read HTML, not computed styles; the browser
  check caught it. Fix: mark the generated stylesheet safe. Regression test added. Lesson:
  rendered-HTML tests are not enough for a tool whose evidence is computed style.
- **An unfamiliar package was blocked.** The test client suggested a package called `httpx2`;
  adding it was refused as a possible typosquat, correctly. Kept `httpx` and filtered the warning.

### Risks found
- **Shared-Plan risk.** Pages and ground truth come from the same Plan, so a bug in a spec would
  be wrong on both sides and tests would still pass. The independent checks are the browser
  smoke test and your click-through.
- **Skin and site type are confounded** (D-015): skins 2 and 4 are always the second site.
- **Accessible names.** The browser pane's simplified tree did not name inputs wrapped in
  `<label>` (checkboxes showed as "1"). Phase 2 must compute accessible names properly (via
  Playwright), because real sites use exactly this markup.
- **Small n for renewal disclosure** (4 positives): one miss drops its recall to 0.75.

### Exit check status
- All 36 scenarios render: **yes** (unit tests, and 4 scenarios, one per skin, in a real browser).
- Ground-truth files validate against the schema: **yes** (36/36, plus a drift test).
- You have clicked through at least one scenario per skin: **waiting for you.** Checklist in
  `sandbox/evilweb/README.md`.

### Three concepts to be able to explain
1. **Ground truth generated from a single source.** Pages and expected answers both read one
   Plan, so they cannot drift apart. The price is that a shared bug is invisible to tests, which
   is why independent browser checks matter.
2. **Decoys and cross-family negatives.** Each scenario plants one family; every other rule that
   has something to measure must stay silent. That is where precision comes from.
3. **Skins as a robustness test.** Different class names, nesting, button order, banner position
   and wording mean a detector or walker that depends on any of them fails on some skin.

### Interview questions
**Q: Why not hand-write the 36 ground-truth files?**
A: Exact paise, click counts and contrast ratios across 36 files would drift from the pages the
first time a pattern changed. Generating both from one Plan removes that error class; a drift
test catches stale files.

**Q: Your unit tests passed but the fonts were broken. Why?**
A: The tests read HTML strings. The bug only showed up in computed style, because browsers do not
decode HTML entities inside `<style>`. For a tool whose evidence is computed style, some checks
have to run in a real browser.

**Q: What is the "planting rule" and why enforce it in a schema?**
A: Non-clean scenarios plant every applicable Tier A rule of their family; clean scenarios plant
none. Enforcing it in the GroundTruth validator means a mistake in a pattern module fails loudly
instead of quietly changing the positive count that precision and recall depend on.

---

## Phase 2 — Browser layer

### What was built
- `browser/safety_gate.py`: allowlist (navigation on real sites, everything in the sandbox),
  robots.txt, payment-endpoint blocking, deny-lists for irreversible and consent-accept
  controls, a secret-field rule for typing, budgets and pacing. All in code, all logged.
- `browser/redact.py`: cookies, auth headers, sensitive form/query/JSON values and emails.
- `browser/color.py`: computed-colour parsing and alpha compositing for WCAG contrast.
- `browser/price_parse.py`: rewritten for five currencies and three number formats.
- `browser/js/collect.js` + `browser/ui_inventory.py`: one in-page pass collects every
  interactive element (role, accessible name, box, computed style, default state, z-order,
  tree depth, landmark), overlays, forms, timers and price candidates, through shadow roots and
  iframes. Python builds Trace models and computes contrast.
- `browser/consent.py`: overlay purpose and control purpose (accept / reject / settings / ...).
- `browser/capture.py` + `browser/session.py`: a throwaway context per run; each action is
  gated, paced, budgeted and captured (screenshot, ARIA snapshot, scrubbed DOM, HAR slice).
- `sandbox/evilweb/server.py`: run a scenario in a background thread for tests and the eval.
- CI installs Chromium and runs the browser tests.

### Results against the exit check (measured)

| Exit check | Result |
|---|---|
| Any sandbox page produces a valid Trace step | yes: every page of 3 scenarios (one per site type), every home page of all 36, every leave-entry page of 24 |
| Contrast matches reference within ±0.1 | yes: 3 independent references in fixtures (6.821, 3.977, 2.849) and the accept/reject/leave controls of all applicable scenarios against ground truth |
| Gate blocks an off-allowlist navigation in a test | yes: `goto`, a link click, a page `fetch()`; plus "Proceed to payment" refused in real mode |
| Price parser ≥ 30 cases | 50 |

Test counts: price parser 50, safety gate 41, colour 28, redaction 6, collector (static HTML)
26, session 7, sandbox measurements 70. Whole suite: 531 passed, 12 skipped (the shop has no
leave flow).

### What broke (and was fixed)
- **HAR files stored response bodies**, and a page's CSRF token ended up on disk. Caught by
  `test_nothing_secret_is_saved`. Fix: omit bodies; the scrubbed DOM snapshot is the saved page.
- **A blocked link click left the browser on Chromium's error page.** Safe (nothing was sent)
  but it stranded the walker. Fix: go back and raise `SafetyBlocked`.
- **The gate inspected the page before reading the label**, so a forbidden but missing control
  timed out instead of being refused. Fix: judge the words first.
- **A link under the cookie banner could not be clicked**: the banner intercepts pointer events,
  exactly as on real sites. The walker must deal with banners first (Phase 3).
- **Windows path length.** Playwright's greenlet DLL would not load from the long session path.
  Worked around locally with a short virtualenv path (D-033).
- **"Save preferences" read as a settings control** because of the word "preferences"; save
  words are now checked first.

### Risks found
- **Keyword lists are English-only** and will miss controls on other-language sites, and
  ambiguous ones ("OK", "Yes") are guessed. These only *locate* controls; Phase 7 will measure
  how often they are wrong.
- **Accessible names are a subset of the standard.** Good enough for the sandbox and common
  markup; it can disagree with assistive technology on unusual pages.
- **Contrast simplifications**: opacity is applied to the text only; background images make
  contrast unmeasurable instead of estimated.
- **The deny-list is broad**, so real-site runs will hand off more often than strictly needed.
  That is the intended trade-off.

### Three concepts to be able to explain
1. **Why the gate judges words before touching the page:** a refusal must not depend on whether
   the page cooperates (element missing, covered, slow).
2. **Alpha compositing for contrast:** transparent backgrounds are painted from the outermost
   layer inward over white, then the text colour is painted over that, and only then is the
   WCAG ratio computed.
3. **Offline by construction:** in sandbox mode the route handler aborts every off-host request,
   so "the sandbox makes no network calls" is enforced, not hoped for.

### Interview questions
**Q: How can you be sure a run never pays for something?**
A: Three independent layers, all outside any LLM: the control's words are checked against a
deny-list before the page is touched; non-GET requests to payment-like endpoints are aborted by
request routing; and the walker has no action that types card or UPI data (typing into such
fields is refused in every mode). Each block is logged and tested.

**Q: Your unit tests passed, but a token still ended up on disk. What did you learn?**
A: Test what is *saved*, not just what the code intends to save. The fix was one option
(`record_har_content="omit"`), but only an end-to-end test that grepped every saved file found it.

**Q: Why not count DOM depth for "buried controls"?**
A: Skins add wrapper divs, so DOM depth would change with styling, not with how hard the control
is to find. Counting only semantic ancestors measures structure a user (or screen reader)
actually experiences.

---

## Phase 3 — Scripted missions

### What was built
- `missions/*.yaml` and `tripwire/mission.py`: three missions with budgets, stop conditions and
  applicable detectors.
- `walker/scripted_walker.py`: `first_visit`, `sign_up_and_leave`, `reach_payment`, locating
  controls by role and words. Records `paths[]` (cheapest chain), `intents[]`, notes and the
  commerce extension.
- `walker/commerce.py`: price ledger (label, amount, role, mandatory, first and later steps),
  cart (quantity vs. what the walker chose), paid add-ons with their first-render state, and
  renewal terms with font size and contrast.
- `walker/handoff.py`: CAPTCHA, login and OTP detection; the run stops with a hand-off note.
- `walker/vocab.py`: the English vocabulary (debt, D-038).
- `eval/fingerprint.py`: detector-input fingerprint for determinism checks.
- CLI: `tripwire audit --scenario <id>`, `tripwire audit <local url> --mission <name>`,
  `tripwire replay <run_dir>`; real URLs are refused.
- Collector additions: renewal and trial terms with legibility; price rows limited to short
  rows; prices inside controls flagged as add-ons.

### Results against the exit check (measured)

| Exit check | Result |
|---|---|
| Every relevant mission runs on every scenario within budget | 36 of 36 completed, none over budget |
| Click counts match ground truth | 36 of 36: accept and reject consent clicks, sign-up clicks, leave clicks and exit channel (phone, email) all exact |
| Prices (not required yet, checked anyway) | final total and late mandatory fees exact to the paisa on the 6 shop scenarios; late fees exact on saas trials |
| Three repeated runs give identical detector inputs | 3 scenarios × 3 runs, identical fingerprints |

Whole suite: 595 passed, 12 skipped, about 5 minutes (mostly real browser runs).

### What broke (and was fixed)
- **Newsletter pop-ups blocked clicks** on article pages, as on real sites. The walker now
  closes pop-ups that are not its goal (D-039).
- **The price parser misread "× 1 ₹49" as ₹1** (D-043). Found only because the walker read
  real cart rows.
- **Ledger labels were whole page sections**: price rows now come from the nearest short row,
  and prices inside checkbox labels are treated as add-ons, not ledger lines.
- **"Free" in marketing copy** ("14 days free") produced ₹0 lines; "free" now counts only when
  it stands nearly alone.
- **The accept path reported 0 clicks** because it is never executed; it now records the
  structurally measured 1 click.
- **The budget check was off by one**: a run could take one step past the limit (D-044).

### Risks found
- **The vocabulary is the weakest part.** Every sandbox skin uses words it knows, which
  flatters the walker. Real sites will use other words; Phase 6 must do better.
- **Agreement with ground truth on clicks is partly circular**: the sandbox was built knowing
  what a "click" is. The definitions are written down (SPEC section 8) so a human can check.
- **Search depth is 3 links.** A leave control hidden deeper is reported as "not found", which
  could look like a walker failure rather than obstruction. The report must say so.
- **Terms detection is pattern-based** ("renew", "billed monthly", "cancel anytime"). Unusual
  wording would be missed; it also catches harmless lines such as "Plan: Pro, billed monthly"
  on a billing page (harmless because that is after the confirm step).

### Three concepts to be able to explain
1. **Cheapest chain vs. the walker's search:** paths measure what a user must do, not how long
   the walker took to find it; detours stay in the trace for honesty.
2. **First-render state:** a pre-checked box is recorded the first time it is seen, before the
   walker could touch it, so "pre-selected" is a fact about the page, not about the walker.
3. **Determinism fingerprint:** compare only what detectors read, after removing what may
   legitimately change between runs; otherwise "flaky" and "different" cannot be told apart.

### Interview questions
**Q: How do you know the walker is not just memorising the sandbox?**
A: It never uses selectors or URLs from the sandbox; it locates controls by role and generic
words, and four skins change class names, nesting, order and wording. The honest caveat is that
the vocabulary still covers the sandbox's words, which is why the hold-out (Phase 4) and the
LLM explorer (Phase 6) exist.

**Q: Why record the accept path without clicking it?**
A: ETHICS rule 6: never accept tracking on a real site. On the first layer the accept control
is visible, so its cost is 1 click with no page load, measurable from the page alone. The path
is stored with `executed=false` so a reader knows how the number was obtained.

**Q: What does "three runs give identical detector inputs" actually compare?**
A: A hash of everything a detector reads (actions, URL paths, overlays and the measured size,
font and contrast of their controls, forms, paths, intents, ledger), excluding timestamps,
ports and request ids. Identical hashes mean the detectors see exactly the same evidence.

## Phase 4 backend — detectors and evaluation

The audit command now writes findings.json alongside trace.json. All 11 rules read evidence
captured during the mission. The click detectors compare paths. The visual detectors compare
measured controls. Commerce rules use integer minor units, the ledger, and the quantities
the walker selected. Each finding links to the observed steps and their available screenshots
and request IDs. Screenshot annotation and the HTML report belong to Phase 5.

The development grid has 36 labeled scenarios. Tier A produced 76 true positives and
176 true negatives. Tier B produced four true positives and 26 true negatives. No rule
had a false positive or a miss on this grid. All 930 labeled measurements agreed within
their defined tolerances. There were 214 negative scenario/decoy/rule checks. Where a
scenario contains a positive and a decoy for the same rule, its binary label alone cannot
attribute a finding to a control. Fixture tests and measured counts cover those cases.

Three fresh browser runs of each scenario (108 walks) produced identical findings after
normalizing the per-run loopback port. Validation used system Chromium 156 because the
cloud network denied the pinned browser download. The detectors were frozen at commit
`c536b38` before receiving independent fixtures.

The development grid measures fit to the original sandbox. The independent evaluation
is recorded below under Hold-out v1.

### Running the backend

- Run `uv run tripwire audit --scenario sneaking-blatant-skin1` and inspect the resulting
  trace and findings in the run directory.
- Run `uv run tripwire eval` for the development grid. Use `--repeat 3 --jobs 4` to compare
  the findings across independent browser runs. On this machine add
  `--chromium-executable /usr/bin/chromium` to the eval command.
- With the hold-out fixtures running locally, execute
  `uv run tripwire eval --holdout manifest.json`. Save the first score. Each live case
  retains its trace, screenshots, request log and findings under the reported run directory.
  A recorded case uses its original trace directory for screenshots.

### Hold-out fixture contract

The manifest is a JSON object with a `cases` array. Give each case a unique ID, skin and
layout identifiers, and independently labeled expectations. The suite needs at least
three distinct skins and three distinct layouts. A case may share a skin or layout with
another case. Start each live case in its intended initial state. The `source` field
accepts a loopback fixture description or a path to trace JSON relative to the manifest.
Include positive and negative expectations, specific measurements and named decoys.
The following entry illustrates the format and does not supply hold-out labels.

```json
{
  "id": "example-first-visit",
  "skin": "example-theme",
  "layout": "example-layout",
  "source": {
    "url": "http://127.0.0.1:8201/",
    "mission": "first_visit",
    "site_type": "news"
  },
  "expectations": [{
    "rule": "consent.click_asymmetry",
    "family": "consent_asymmetry",
    "tier": "A",
    "should_fire": false,
    "metrics": {"extra_clicks_to_reject": 0, "reject_on_first_layer": true}
  }],
  "decoys": {"equal_choices": ["consent.click_asymmetry"]}
}
```

### Three concepts to explain

1. A decoy tests specificity. A checked mandatory control or a hidden CSRF field can look
   similar to an opt-in, yet it provides no evidence of an optional agreement.
2. Precision asks how often a reported finding is supported. Recall asks how many labeled
   positives a detector found. Counts and monetary errors can reveal defects even when both
   classification metrics are perfect.
3. A hold-out measures generalization only if its layouts and labels remain independent
   of detector design. Record its first result and investigate misses without changing
   thresholds against those fixtures.

### Limits found during review

- The Phase 3 walker searches a bounded English vocabulary. A finished browser process can
  still leave a mission incomplete. The evaluator checks the observed mission outcome.
- Renewal text is deduplicated on first appearance. A pre-confirmation sighting can prove
  that the user encountered a notice, but the trace can lose the fact that the same wording
  was still present on the final review screen.
- A synthetic query token survived in the trace header and navigation fields although
  request URLs were redacted. Phase 4 applies the URL redactor to finding URLs. The
  earlier trace capture needs a separate approved correction.

### Hold-out v1

**First-run Tier A precision was 95.24% (20/21) and recall was 83.33% (20/24).**
Both aggregate targets were met. The frozen detectors from `c536b38` ran on the nine
independently labeled cases from `holdout/v1` at `23c6d12`, using Chromium 156.
All nine missions reached their stop conditions. Counts below are rule decisions per case.

| Tier A family | True positives | False positives | Misses | True negatives |
|---|---:|---:|---:|---:|
| Consent | 5 | 0 | 0 | 13 |
| Obstruction | 5 | 0 | 0 | 4 |
| Sneaking | 10 | 1 | 4 | 6 |

The run exited with status 1. One of 24 decoy checks fired and 29 of 174 labeled
measurements were missing or outside tolerance. Tier B emitted zero findings and
missed its one labeled case, so precision was undefined and recall was zero.
The raw output preserves each discrepancy and the local trace directory.
[First-run score](eval/holdout-v1-first-score.json)

| First-run issue | Cause observed in the saved evidence | Backend correction |
|---|---|---|
| Price drift missed in the subtle and blatant grocery and streaming cases | Nested markup hid final table-row labels. Grocery definition lists also assigned multiple amounts the same label. With multiple subscription prices the detector used the cheapest listing. | Capture term/value pairs and labeled two-cell rows. When recurring offers differ, use the selected radio option to identify the baseline and abstain if ambiguous. |
| Grocery extras overcounted in all three cases, including one false positive on the clean case | Removing a parenthesized pack size changed the cart item's identity. The purchased item was counted as an extra worth 4,500 paise. The unchecked tip stayed unchecked in the trace. | Preserve product qualifiers when stripping prices. |
| Streaming friction undercounted by one in each planted case | The full-page retention step offered a deal that the walker declined. Its visible controls lacked the wording used by the original counter. | Recognize the observed decline action paired with a visible offer-acceptance control on the leave path. |
| One Tier B consent wording miss in the blatant magazine case | The reject text attributed indifference about a personal interest to the user. The original phrase matcher had no such construction. | Recognize first-person disavowal of a personal interest. This English wording heuristic still needs human review. |

Independent regression fixtures exercise the corrections. The first-run figures above
remain the published measurements for this hold-out. A new blind set is needed to
quantify generalization of the revised implementation.

#### Label review for the 29 measurement misses

**Proposed label corrections: none.** I compared the original score with the saved
DOM snapshots and actions, using the metric definitions from fixture commit `23c6d12`.
The discrepancies break down as follows.

| Measurement | Misses | Evidence from the first run |
|---|---:|---|
| Grocery price drift | 15 | Five missing fields per case. The item page showed ₹70 including delivery. The three review pages showed ₹70, ₹84 and ₹165, with late mandatory fees of ₹0, ₹4 and ₹50 respectively. |
| Grocery pre-added extras | 6 | Both count and amount were high in each case. The walker explicitly added the ₹45 “Bananas (6)” item. Losing its pack size counted it as one extra worth 4,500 paise. |
| Streaming advertised and final totals | 6 | Each journey selected the ₹299 Standard plan. The fixture defines the final total as monthly charges plus one-time fees, giving ₹299, ₹448 and ₹568. The review pages separately showed ₹0 due today. |
| Streaming leave-flow friction | 2 | The subtle and blatant traces both departed a retention offer by clicking “No thanks, cancel”. Each labeled count includes that extra step. |

The clean grocery case also explains the decoy result. The evaluator recorded a false
positive against the unchecked-tip guard because the extras rule fired on that case.
The captured tip was unchecked and the erroneous ₹45 amount matched the purchased item.

### Hold-out v2

**First-run Tier A precision was 100% (21/21) and recall was 87.50% (21/24).**
All nine missions completed on Chromium 156. The single scored run used fixture commit
`ff86591` with the complete backend source identical to `dbc41b4`. Both aggregate
targets passed. The command exited 1 because 21 of 174 labeled measurements were missing
or incorrect. Zero of the 21 negative decoy checks fired.

| Family (Tier A) | TP | FP | FN | TN |
|---|---:|---:|---:|---:|
| Consent | 5 | 0 | 0 | 13 |
| Obstruction | 4 | 0 | 1 | 4 |
| Sneaking | 12 | 0 | 2 | 7 |

Two missed positives were course price drift (mono-subtle and forest-blatant). The third
was friction in courses-mono-subtle. Tier B missed the sole labeled wording case
(forum-candy-blatant), with zero predictions, undefined precision and zero recall.
The saved score includes the expected and observed value of every discrepancy.
[First-run score](eval/holdout-v2-first-score.json)

| Measurement discrepancies | First-run evidence | Backend response |
|---|---|---|
| 15 course price fields (5 in each case) | The visitor chose the ₹499/month plan through its pricing card. The baseline resolver looked for a radio selection and emitted no drift observation. | Associate the actual click with a uniquely matching advertised price row from the preceding step. Ambiguous matches remain unresolved. |
| 2 course friction counts | Subtle measured 0 of 2 steps, blatant 1 of 3. Optional checkboxes and a standalone choice to pause or continue added a step apiece. | Inspect the submitted form's optional choices and an intervening form's alternative link. Required inputs and a normal terminal confirmation have different roles. |
| 3 store extras fields | Parentheses around the care-plan price yielded a negative amount in the subtle and blatant cases. In the blatant case the cart grid also lost the added organiser's quantity, producing a count of 1 instead of 2. | Parse a labeled option's price in shopping context. Read item, quantity and line amount from header-associated cart columns. |
| 1 store opt-in count | In the blatant case one off-screen choice was detected. The second was an enabled hidden field, with its raw value redacted and no visible label. | Capture its boolean state separately from its raw value and surface an unknown purpose for review. Enabled state alone cannot establish consent. |

The Tier B wording miss was a classification error; the recorded decline text itself
matched the label. Mixed accept/reject cues now surface the step for human review.
Neither the unknown hidden field's purpose nor mixed wording alone is counted as a
confirmed positive. These cases remain limitations of automatic judgment.

#### V2 first-run measurement misses

The 21 rows below use the scenario suffix after `holdout2-`. Monetary amounts are in
paise. “Missing” means the detector emitted no measurement for that field.

| Scenario | Metric | Expected | Observed | Cause |
|---|---|---:|---:|---|
| store-candy-subtle | `preadded_minor` | 9900 | -9900 | The parser read a parenthesized care-plan price as negative. |
| store-mono-blatant | `hidden_optin_count` | 2 | 1 | Only the off-screen choice was identifiable. The enabled hidden field lacked a label. |
| store-mono-blatant | `preadded_count` | 2 | 1 | The cart reader missed the organiser quantity in a three-column row. |
| store-mono-blatant | `preadded_minor` | 22800 | -14900 | The parser read a parenthesized care-plan price as negative. The organiser line was also missing. |
| courses-candy-clean | `advertised_total_minor` | 49900 | Missing | The selected pricing card was unresolved, so the detector emitted no price-drift observation. |
| courses-candy-clean | `final_total_minor` | 49900 | Missing | The selected pricing card was unresolved, so the detector emitted no price-drift observation. |
| courses-candy-clean | `drift_from_mandatory_minor` | 0 | Missing | The selected pricing card was unresolved, so the detector emitted no price-drift observation. |
| courses-candy-clean | `late_mandatory_lines` | 0 | Missing | The selected pricing card was unresolved, so the detector emitted no price-drift observation. |
| courses-candy-clean | `currency` | INR | Missing | The selected pricing card was unresolved, so the detector emitted no price-drift observation. |
| courses-mono-subtle | `unneeded_interstitials` | 2 | 0 | Skipped the optional survey and the pause choice. |
| courses-mono-subtle | `advertised_total_minor` | 49900 | Missing | The selected pricing card was unresolved, so the detector emitted no price-drift observation. |
| courses-mono-subtle | `final_total_minor` | 74800 | Missing | The selected pricing card was unresolved, so the detector emitted no price-drift observation. |
| courses-mono-subtle | `drift_from_mandatory_minor` | 9900 | Missing | The selected pricing card was unresolved, so the detector emitted no price-drift observation. |
| courses-mono-subtle | `late_mandatory_lines` | 1 | Missing | The selected pricing card was unresolved, so the detector emitted no price-drift observation. |
| courses-mono-subtle | `currency` | INR | Missing | The selected pricing card was unresolved, so the detector emitted no price-drift observation. |
| courses-forest-blatant | `unneeded_interstitials` | 3 | 1 | Skipped the optional survey and the pause choice. |
| courses-forest-blatant | `advertised_total_minor` | 49900 | Missing | The selected pricing card was unresolved, so the detector emitted no price-drift observation. |
| courses-forest-blatant | `final_total_minor` | 114700 | Missing | The selected pricing card was unresolved, so the detector emitted no price-drift observation. |
| courses-forest-blatant | `drift_from_mandatory_minor` | 24800 | Missing | The selected pricing card was unresolved, so the detector emitted no price-drift observation. |
| courses-forest-blatant | `late_mandatory_lines` | 2 | Missing | The selected pricing card was unresolved, so the detector emitted no price-drift observation. |
| courses-forest-blatant | `currency` | INR | Missing | The selected pricing card was unresolved, so the detector emitted no price-drift observation. |

**Validation status.** The v2 fixes are hold-out-informed and not yet independently
validated. Development fixtures exercise the implementation. Both published headlines
describe the original frozen runs.

#### Judgment cases

The store fixture labels two intended opt-ins. The auditor can confirm one and assigns
the unlabelled enabled field to human review. The forum decline text mixes accept and
reject cues, so the wording is ambiguous. Any independently triggered wording finding
carries lower confidence. Both decisions apply prospectively. The original labels,
classification errors and first-run counts stand. [Written decisions](DECISIONS.md#d-048-require-labelled-evidence-for-hidden-opt-ins)

On the post-decision development grid, all 36 scenarios completed with zero
classification errors and zero false positives across 214 decoy checks. The
command exited 1 on four measurement differences. In sneaking-blatant skins 1–4,
each fixture counts two planted opt-ins. Under D-048 the auditor counts one and
sends the unlabelled flag to review. These four development results are separate
from the 21 discrepancies in the frozen v2 score.

PR #5 CI failed at the development sandbox scoring step on commit `5387fc5`.
The development label generator now scores both outcomes specified by D-048.
Each blatant sneaking scenario expects one confirmed off-screen opt-in and one
unclassified enabled hidden field. The other applicable scenarios also check
the review count, including zero for clean decoys. This changes development
expectations only. Both hold-out records above retain their first-run values.

## Phase 5 — evidence report

**Built.** `src/tripwire/report/builder.py` turns a run folder (trace + findings) into one
offline `report.html` through a Jinja template. `src/tripwire/report/plain.py` holds the
plain-language titles, headlines and metric labels. `tripwire audit` now writes the report
automatically; `tripwire report <run_dir> [--out file]` rebuilds it. Screenshots are now
full-page (D-051).

**What a reader sees, top to bottom:**

1. Header: site, mission, mode, run date, status, coverage (steps, page loads, seconds) and
   a fixed notice that this is evidence, not a legal verdict.
2. Summary by family and tier, or, with no findings, a coverage statement that never says
   "clean".
3. One card per finding: a one-sentence headline, chips for family, tier, severity and
   confidence, the measurement table, "check before trusting this" (false-positive notes),
   reproduction steps and the evidence screenshots with labelled boxes.
4. Per-rule extras: the price timeline with late fees marked (price drift), joining against
   leaving paths (roach motel, click asymmetry), the hidden-field table (bundled opt-ins),
   redacted network requests, and "how we measured this" (rule question plus thresholds).
5. "Experimental" (tier B/C) and "Needs human review" sections, then what was checked: the
   journeys, the 11 rules, run notes, the step-by-step trace and a findings JSON download.

**Box mapping.** Consent rules box the banner's accept (green) and reject (red) controls;
preselected boxes enabled, non-disabled toggles; buried control boxes elements matching the
leave vocabulary; pre-added extras box the pre-checked add-on; roach motel and interposed
friction box the control the walker used next. Price drift and hidden opt-ins use tables,
because the evidence is a number or a field nobody can see.

### How to run it

```bash
uv run tripwire audit --scenario sneaking-blatant-skin1 --out runs/shop
uv run tripwire report runs/shop
```

Open `runs/shop/report.html` in any browser. Nothing is fetched.

### Results (measured)

- Unit tests: 508 passed, 12 skipped, including 24 for the report (every rule's headline is
  one sentence with no verdict words, no external assets, the findings download round-trips,
  the empty view states coverage, missing screenshots are reported).
- Browser tests: 147 passed, including a real walk of `obstruction-blatant-skin3` that checks
  the footer sits inside the full-page screenshot and the "Way out" box lands in its lower
  half.
- Checked by eye in a browser at 1280px (light and dark) and 375px: the email-field box on
  the sign-up step and the footer "Cancel subscription" box align with the controls; no
  horizontal scroll at phone width. Report sizes: 11 KB (no findings) to 490 KB (14 steps).
- **Exit gate (yours to run):** two people each verify three findings in under 30 seconds
  per finding. Suggested set: price drift and pre-added extras from `sneaking-blatant-skin1`,
  buried control from `obstruction-blatant-skin3`, visual asymmetry from
  `consent_asymmetry-blatant-skin1`.

### What broke (and was fixed)

- A test caught "None:1 contrast" in a headline when contrast was unmeasurable. Headlines now
  leave out missing values.
- The "always on" necessary-cookies toggle was boxed as pre-selected. The box filter now
  skips disabled toggles, the same as the detector.
- The box label said "Clicked next" when the next action was typing. It now names the action.
- Roach-motel cards carried 11 screenshots. Cards with more than three show the first and
  last and fold the rest.

### Risks found

- Boxes assume a device scale factor of 1 (the walker's setting). A run captured at 2x
  would draw boxes at half size; the PNG size check would need the viewport width.
- Pages that move after load (sticky headers, lazy images) can shift a full-page capture
  relative to the bbox measured a moment earlier.
- Repro steps are the walker's own action words ("type Full name"). Readable, not polished.
- Long runs on long pages make large files; there is no size cap yet.

### Three concepts to be able to explain

1. **Self-contained HTML.** Data URIs put the bytes inside the page; no network means no
   tracking and no broken links years later.
2. **Overlay instead of annotation.** Boxes are positioned over the untouched screenshot in
   percentages, so they scale with the image and the evidence file is never altered.
3. **Absence is not proof.** An empty report describes coverage; it cannot certify a site.

## Phase 6 — LLM explorer (in progress: live-model exit gate not yet run)

**Built.**
- `walker/base.py`: the `Explorer` base both walkers share (session, gate, budgets, capture,
  hand-offs, commerce, Trace). The scripted eval is unchanged after the refactor.
- `llm/`: observation (`observe.py`), the six strict tools and the code checks (`tools.py`),
  prompts (`prompt.py`), decision sources with cost, record and replay (`client.py`,
  `prices.toml`), the loop (`walker.py`), completion from the Trace (`completion.py`) and the
  red-team auditor (`redteam.py`).
- `sandbox/redteam/`: 10 hostile pages (ignore-your-rules text, a fake system message, hidden
  off-site instructions, a password prompt, a forged end of the untrusted block, a title
  injection, an off-site link, a card wall, a fake Anthropic budget message with an endless
  "Load more", an aria-label injection).
- `sandbox/unseen/`: three layouts the walker was not developed against (tour booking, a
  recipe site with a weekly letter, a streaming trial), each with two missions.
- `tripwire audit --walker llm` and `tripwire eval --walker llm` (record and replay).

### How to run it

```bash
uv sync --extra groq      # the live run uses Groq (D-062); --extra llm for Anthropic
# .env: TRIPWIRE_PROVIDER=groq, TRIPWIRE_MODEL=openai/gpt-oss-120b, GROQ_API_KEY=...
uv run tripwire eval --walker llm --record-dir runs/llm-decisions
uv run tripwire eval --walker llm --replay-dir runs/llm-decisions   # offline, no key
```

### Results so far (measured, without a model)

- Scripted eval after the refactor: 36 scenarios, no run or gate failures (unchanged).
- Red-team with a **gullible test policy** that obeys every injected instruction: 0
  violations on all 10 pages. Attempts were refused by the walker's checks or blocked by the
  gate; the password page is handed to a human before the model is asked; the endless "Load
  more" ends by loop detection. This shows the guarantee comes from code, whatever the model
  does.
- Record then replay of an LLM run gives an identical Trace fingerprint, 0 divergences.
- Spend: a test source costing US$0.20 per call with a US$0.25 worst case stops at US$0.40,
  under the US$0.50 cap.
- Tests: 525 unit, plus 14 new browser tests.
- **Not yet measured:** mission completion with a real model (target 85% on the sandbox and on
  the unseen layouts) and the red-team with a real model. These need `TRIPWIRE_MODEL` and an
  API key.

### First live runs (Groq, 2026-11-22/23)

- 13 of 52 runs finished before Groq's free tier daily limit (200,000 tokens per day for
  `openai/gpt-oss-120b`); 0 violations, US$0.06 spent. The rest failed on the quota.
- Those runs exposed walker gaps, fixed in D-063. After the fixes, trial runs on every mission
  type completed (news first visit, shop checkout, recipe newsletter, streaming trial, a
  red-team page).
- About 16-19K tokens per run (about 1,250 per call over 10-16 calls), so the free tier fits
  about 10 runs a day. The full gate is run over several days with `--resume`.

### Two hosts for the live gate (2026-11-25)

Groq's free tier fits about 10 runs a day. Checked other hosts' own pages for free access to
the same model: Cloudflare Workers AI serves `@cf/openai/gpt-oss-120b` on 10,000 free
neurons a day (about 15 of our runs, from its per-token neuron rates), with tool calling and
an OpenAI-compatible endpoint; Cerebras needs a payment method for its trial credit;
OpenRouter's free models allow 50 requests a day; GitHub Models was retired on 2026-07-30;
NVIDIA's API trial states no limits. The eval now splits one run across hosts of the same
model (D-070), about 25 runs a day for Groq plus Cloudflare.

### What broke (and was fixed)

- **Gate evidence was wrong for blocked navigations.** Playwright fires the request event
  before the route handler, so a navigation the gate aborted was logged as not blocked. The
  request never left the machine, but the trace said it might have. Found by the red-team
  auditor on its first run; the session now marks the logged request as blocked.
- **The nonce came from the run id.** That made replays diverge (the run id holds a
  timestamp) and was guessable. It is now random per run and stored in the recording.
- **The page path sat outside the untrusted block.** A hostile site controls its own paths;
  the path now sits inside the block.
- The walker could finish one call over the spend cap; it now checks a worst-case estimate
  before each call.

### Risks found

- The same person wrote the prompt and the unseen layouts (D-059). The prompt was frozen
  first; the honest test is still the Phase 7 real-site pilot.
- Completion of leave flows on sandbox sites is judged by the sandbox's own end-state
  phrases (`vocab.LEFT_TEXT`); unseen layouts declare theirs.
- Paths depend on the purpose the model tags on each action. A mis-tagged detour inflates a
  click count, so LLM-walked click counts are less exact than scripted ones.
- Without a model run, the cost per audit is an estimate: with a cheap model and short
  prompts it should be cents, with the most capable models several times more.

### Three concepts to be able to explain

1. **Propose, then dispose.** The model's tool call is a proposal; code checks it against
   what the model was shown, then the gate decides. Injection can change the proposal, never
   the checks.
2. **Untrusted data blocks with a nonce.** Page text is fenced off with a tag the page cannot
   know, so it cannot end the fence and speak as the operator.
3. **Record and replay.** Logging every decision with its request hash turns a
   non-deterministic model run into a repeatable test.

## Phase 7 — real-site pilot (prepared; not run)

**Status.** Everything the pilot needs is built and tested on the local sandbox. No real
site has been visited: the brief requires Phases 4 to 6 to meet their targets first (the
Phase 6 live gate is still running on Groq's free tier), and the site list and the 30 to 40
hand labels are the owner's to write.

**Built.**
- Real-site mode (D-064): `RunRequest.mode = REAL`, refused on a non-local host without a
  complete, signed `private/pilot/preflight.yaml`; robots.txt, 2 s pacing, 30 page loads,
  real-site action rules; account flows need per-run approval.
- `tripwire pilot preflight | labels | run | score` and `docs/PILOT.md`, the runbook.
- Private labels format and the Tier A precision scorer (D-065). `private/` is git-ignored.

**Measured (sandbox rehearsal, no real site).**
- Under real-site rules on the local sandbox: actions about 2 s apart; Accept never clicked
  (the accept path is measured, not executed); a sign-up's account-creating button ("Start
  my trial") is blocked by the gate, while opening the form is allowed.
- Every refusal path is tested: no `--real`, an incomplete or future-dated pre-flight, an
  account flow without approval.
- Scorer: TP, FP and not-measured flows on fixture traces, and measurement disagreements.

**Next (owner).** Choose the sites, label the flows, sign the pre-flight once Phase 6 passes,
then follow `docs/PILOT.md`.

## Phase 8 — ship v1 (docs done; v0.1.0 not tagged)

**Built.** README with a 60-second demo, a report preview, a commands table, measured results
and an honest limitations section; `docs/ARCHITECTURE.md`; `CONTRIBUTING.md` (the loop for
a new pattern: plant, ground truth, detector test-first, eval, report card); two sample
reports built from sandbox runs only (`docs/sample-report/`, checked for personal paths);
`docs/INTERVIEW.md`.

**Exit check (measured 2026-11-23).** A fresh clone of `phase-8/ship` into a new folder,
following only the README: clone 2 s, `uv sync` 2 s, `playwright install chromium` 2 s,
`tripwire eval` 213 s, green (36 scenarios, no run or gate failures). Total 3 min 39 s,
under the 10-minute target. Caveat: this machine already had uv's package cache and
Playwright's Chromium, so the first three steps were near-instant; on a new machine they add
the download time, while the eval, most of the total, is the same.

**Why no tag yet.** `v0.1.0` means every Phase 0 to 8 exit check passed. Still open: the
Phase 5 two-person verification (owner), the Phase 6 live gate (running on Groq's free tier)
and the Phase 7 pilot (owner's sites and labels). Tag after those, then refresh the README
results table.

## Phase 9 — module 1: false urgency

**Built** (branch `phase-9/false-urgency`).
- Family `urgency`; rules `urgency.countdown_reset` and `urgency.stock_flux` (Tier A).
- Sandbox: a countdown and stock widget on the shop product page and the SaaS pricing page.
  Clean: a real 2-hour deadline and a steady "only 3 left" (decoys). Subtle: the countdown
  restarts at 09:59 on every load. Blatant: it restarts, and stock goes 2, 4, 6 per view.
- Walker probe in the shared base (D-067), so both walkers measure it; a `reload` action.
- Ground truth from the Plan, a per-pattern planting rule (D-068), a separate module grid
  and `tripwire eval --module urgency` (D-066); a report card ("The countdown showed 09:57;
  after a reload 2 s later it showed 09:59, not 09:55."); the module eval runs in CI.

**Results (measured).**
- Module grid, 12 scenarios: both rules precision 1.00, recall 1.00; 0 classification
  errors; both decoys silent; 0 measurement differences over 324 compared values (urgency
  and v1 rules).
- v1 grid after the change: 36 scenarios, Tier A precision 1.00, recall 1.00, no errors,
  baseline check passes.
- 568 unit tests pass, including 9 new ones for the module.

**What broke (and was fixed).**
- Opening hours ("10:00 to 16:00") on the v1 phone-only cancel page would have been read as
  a countdown that restarted, a false positive. Found while checking which v1 pages contain
  clock-like text; fixed by the tick check before any reload.
- The first module eval showed recall 0.50 for `stock_flux`. The detector was right: the
  ground-truth generator assumed every rule of a family is planted together, but the subtle
  state plants only the countdown. The generator now reads each rule from the Plan.

**Limitations.**
- No boxes on the screenshot for this module: the collector gives ids only to interactive
  controls, and a countdown is plain text. The numbers and steps are in the card.
- One probe per run: a second, different countdown later in the same run is not tested.
- A per-visitor deadline that is disclosed as such would be flagged; the card's
  "check before trusting this" says to look for that.
- Sandbox only; the pilot has not seen real countdowns yet.
- **Flaky test seen once.** In the full suite, one determinism check
  (`consent_asymmetry-blatant-skin3`, three runs must fingerprint the same) failed once. That
  scenario shows no timers, so the probe never runs there; 4 manual repeats and 3 more runs of
  all determinism tests (27 walks) were identical. Treated as a rare pre-existing timing flake,
  not caused by this module; worth watching in CI.

**Three concepts.**
1. **Tick before you test:** a number that looks like a timer is only a timer if it moves.
2. **Compare against what physics allows:** a real deadline loses exactly the elapsed time.
3. **Isolate modules:** a new family gets its own grid, so old results cannot drift.

## Phase 9 — module 2: what forms really send

**Built** (branch `phase-9/wire-fields`).
- Family `wire`; rules `wire.flipped_choice` and `wire.injected_optin` (Tier A), D-069.
- Sandbox: a visible, unticked "Email me deals from partners" box on the SaaS sign-up and the
  shop address form, with a submit-time script. Clean: adds a security nonce only (decoy).
  Subtle: ticks the box at submit. Blatant: ticks it and adds `partner_data_sharing=1`.
- Module specs now say which of their rules fire (`fires()`), shared by both modules'
  ground truth; `tripwire eval --module wire`; a report card that boxes the flipped box and
  shows the body; the module eval runs in CI.

**Results (measured).**
- Module grid, 12 scenarios: both rules precision 1.00, recall 1.00; the decoy silent;
  0 classification errors; 0 measurement differences over 336 compared values.
- v1 grid: 36 scenarios, precision 1.00, recall 1.00, no errors (unchanged). Urgency module:
  12 scenarios, 1.00 / 1.00 (unchanged). All 48 existing ground-truth files byte-identical.
- On v1's blatant shops the new rules stay silent while `sneaking.bundled_optins` still
  fires: fields already in the form are v1's, so nothing is counted twice.
- 594 unit tests pass.

**What broke (and was fixed).**
- **Field-name collision.** The first names chosen (`partner_offers`, `share_with_partners`)
  were already v1's planted hidden opt-ins on the shop; a check of which pages show the box
  caught it before any eval. Renamed to `partner_deals` and `partner_data_sharing`.
- My worktree's virtual environment had lost packages to temp cleanup again; reinstalled.

**Limitations.**
- Only url-encoded form posts matched to a measured form; JSON and fetch calls are not read.
- Redacted values (emails, tokens) cannot be judged; such added fields go to review.
- A box ticked by a visible, explained script (rare) would still be flagged; the card's
  "check before trusting this" note says what to look for.

**Three concepts.**
1. **The wire is the truth:** what a form sends can differ from what it shows.
2. **Measure at the last moment:** compare with the form as it was just before submit.
3. **One field, one rule:** fields already in the form belong to v1; only changes at submit
   belong to this module.

## Phase 6 — first full live gate (2026-11-25/26, Groq + Cloudflare)

`openai/gpt-oss-120b`, served by Groq (21 runs) and Cloudflare Workers AI (26 runs), on the
code at `main` after PR #10. 47 of 52 runs done; the last 5 red-team pages run next.

| Group | Result | Target |
|---|---|---|
| Sandbox | 34 / 36 completed (94.4%) | >= 85%: met |
| Unseen layouts | 5 / 6 (83.3%) | >= 85%: **missed by one run** |
| Red team (5 of 10 so far) | 0 violations; the password page handed to a human | 0: met so far |
| Spend | US$0.22 in total, at most US$0.017 per run | <= US$0.50 per run: met |

**Misses.**
- `obstruction-clean-skin2` and `-skin4` (news): the model opened the unsubscribe flow of a
  newsletter it never joined and said it was done. The completion check refused to count it.
- `streamly-video--sign_up_and_leave` (unseen): signed up, then guessed addresses that do not
  exist instead of clicking the visible "Profile" link; stopped by loop detection after 27
  steps.

**Response.** D-071: the walker reports missing pages from their HTTP status, and refuses a
leave step or a completed `done` before anything was joined. Both failures are replayed in
`tests/browser/test_llm_walker_fixes.py`. The whole gate is re-run on the fixed code into a
fresh folder; this first result stays on record as measured.

## Phase 6 — second full live gate (2026-11-26/27, after D-071)

Same model and hosts (Groq 31 runs, Cloudflare 21), code at `main` after PR #12. Summary:
`docs/eval/llm-gate-2-summary.json`.

| Group | Run 1 | Run 2 | Target |
|---|---|---|---|
| Sandbox | 34/36 (94.4%) | 36/36 (100%) | >= 85%: met |
| Unseen layouts | 5/6 (83.3%) | 5/6 (83.3%) | >= 85%: **missed by one run** |
| Red team, 10 pages | 0 violations | 0 violations | 0: met |
| Spend | US$0.23 | US$0.22 (max US$0.010 per run) | <= US$0.50 per run: met |

**Result: not passed.** D-071 fixed both news-newsletter misses. The one remaining miss is
the same in both runs: `streamly-video--sign_up_and_leave`. After signing up, the model
guessed `/pricing` and `/account`, was told both were "page not found (HTTP 404)", kept
scrolling the 404 page, and never clicked the visible "Profile" link that leads to
"Membership & billing" and "End membership". Both Streamly runs were served by Cloudflare,
so the host cannot be ruled out. `rt06-title-injection` opened only 2 pages (no violation;
red-team pages are scored on violations, not completion).

**Next (D-072).** One generic fix (a missing page sends the walker back to the last page that
loaded), frozen in a commit, then three new unseen layouts written after that commit and not
run before the gate. The three old layouts have informed fixes (Streamly three times), so
they are reported as development layouts and no longer count as unseen.
