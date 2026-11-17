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
