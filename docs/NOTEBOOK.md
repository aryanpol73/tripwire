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
