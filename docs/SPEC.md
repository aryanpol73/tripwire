# Tripwire — Specification (v1)

Status: **draft for review** (Phase 0 exit check). Numbers marked *(cfg)* are default
thresholds. In Phase 4 they move into a config file; they are never hard-coded in a rule.

## 1. What Tripwire does, in one paragraph

Tripwire opens a website the way a person would, performs a short **mission** such as "first
visit" or "sign up, then try to leave", and records everything it saw and did. Then a set of
**detectors** reads that record and looks for measurable asymmetries: rejecting cookies takes
more clicks than accepting them, a fee appears only at the last step, cancelling takes six
clicks when signing up took two. Each result is a **finding** with the numbers, screenshots
and steps needed for a human to check it in 30 seconds. Tripwire reports evidence. It never
says a site is illegal or acted on purpose.

It works on any kind of site: shops, news, SaaS, booking, sign-up forms. The engine stays the
same; the mission and the detectors that apply change.

## 2. The pipeline

```
Mission  ->  Walker  ->  Trace  ->  Detectors  ->  Findings  ->  Report
(YAML)      (browser)    (JSON)    (pure code)    (JSON)        (static HTML)
```

| Piece | What it is | Touches a browser? |
|---|---|---|
| **Mission** | A named user journey: goal, start URL, allowed domains, budgets, stop condition, and which detectors apply. A small YAML file in `missions/`. | no |
| **Walker** | Runs a mission in a real browser and writes a Trace. Scripted for the sandbox (Phase 3), LLM-driven for unfamiliar sites (Phase 6). Every action passes through the safety gate. | **yes** |
| **Trace** | One JSON file plus screenshots, accessibility snapshots, DOM snapshots and network logs, for one run of one mission on one site. Self-contained: it holds every measurement a detector needs. | no |
| **Detector** | A pure function: Trace in, list of Findings out. Belongs to a pattern family and a tier. Testable in milliseconds against fixture Traces. | no |
| **Finding** | One measured asymmetry with evidence, reproduction steps and notes on what to double-check. | no |
| **Report** | One self-contained HTML file per run. | no |

Two support pieces: **Evil Web**, a sandbox of fake sites (shop, news, saas) with planted
patterns and known answers; and the **eval harness**, which runs everything on the sandbox and
scores precision and recall against those answers.

**Why observing and judging are separate:** the browser part is slow and flaky; the judging
part is logic. With a saved Trace in between, a detector can be tested without a browser,
re-run offline after a rule changes, and checked by someone who never runs the tool.

### 2.1 v1 missions

| Mission | Journey | Families |
|---|---|---|
| `first_visit` | Land, handle any consent banner, scroll, open 2–3 internal pages | consent asymmetry, obstruction |
| `sign_up_and_leave` | Find a sign-up, newsletter or trial; then find how to cancel, unsubscribe or delete | consent asymmetry, sneaking, obstruction |
| `reach_payment` | Add something to a cart or start a booking; go to the last page before payment | sneaking |

Each mission is a YAML file in `missions/` (goal, start path, budgets, stop condition,
applicable detectors); see DECISIONS D-034.

### 2.2 Detector tiers

| Tier | How it decides | Max confidence | Counts toward headline metrics? |
|---|---|---|---|
| **A** | Deterministic measurement (counts, computed styles, default states, price ledgers) | 1.0 | yes |
| **B** | Heuristics, optionally with LLM help on the ambiguous remainder | 0.75 | no, reported separately |
| **C** | LLM judgement only; experimental | 0.4 | no, never a headline finding |

The confidence caps are enforced by the Finding schema (DECISIONS D-008).

## 3. The three v1 pattern families

Every rule needs three things before it counts as done: a measurable definition, thresholds
in a config file, and **decoys** (legitimate look-alikes it must not flag). No rule claims
intent or illegality; it reports a measured asymmetry. Tier A rules ship first.

### 3.1 Consent and choice asymmetry
Missions: `first_visit`, `sign_up_and_leave`. The "yes" path is easier or more prominent than
the "no" path.

| Rule | Tier | Measured as | Fires when *(cfg)* |
|---|---|---|---|
| Click asymmetry | A | clicks and page loads to reject vs. accept, from the first banner layer (`paths[]`) | reject needs ≥ 2 more clicks than accept, **or** no reject control on layer 1 |
| Visual asymmetry | A | area, font size and contrast ratio of the accept vs. reject controls (`overlays[].controls` → `ui.elements[]`) | area ratio ≥ 3, **or** reject contrast < 3:1 while accept ≥ 4.5:1 |
| Pre-selected consent | A | default `checked` state of non-essential toggles, marketing opt-ins, newsletter boxes | any such box is checked by default |
| Confirm-shaming / trick wording | B | decline text matched against a phrase list; an LLM may rate only the unmatched remainder | phrase match; confidence medium at most |

Decoys: equal-weight Accept and Reject; a locked-on "strictly necessary" toggle (`disabled`
and `checked`, so not a choice); a settings page whose optional boxes are unchecked.

On real sites the accept path is never executed. It is measured structurally from the page
(`paths[].executed = false`).

### 3.2 Sneaking and hidden extras
Missions: `sign_up_and_leave`, `reach_payment`. Something is added, or costs more, without
the user choosing it.

| Rule | Tier | Measured as | Fires when *(cfg)* |
|---|---|---|---|
| Price ledger drift | A | `commerce.price_ledger`: the lowest total (or item-sum) shown before the last step vs. the final total, in integer minor units | any positive drift caused by **mandatory** lines that first appeared later |
| Pre-added extras | A | `commerce.cart[].qty_added_by_walker` vs. `qty`; `commerce.default_addons[].preselected` | an item, add-on, donation, insurance or upgrade the walker did not add, or a pre-checked paid add-on |
| Trial and renewal disclosure | A/B | presence of renewal price/date before the confirm button; its font size and contrast | missing, or shown below 3:1 contrast or under 12 px. "Too subtle" stays Tier B |
| Bundled opt-ins | A/B | `forms[].fields`: `hidden`, `off_screen`, `prechecked`, `default_value` | a hidden, off-screen or pre-checked field that changes what the user agrees to |

Decoys: tax shown as "+ taxes" from the first page; shipping the walker explicitly chose; a
pre-checked "remember me"; hidden CSRF inputs.

### 3.3 Obstruction
Missions: `sign_up_and_leave`, `first_visit`. Leaving or declining is harder than joining or
accepting.

| Rule | Tier | Measured as | Fires when *(cfg)* |
|---|---|---|---|
| Roach-motel asymmetry | A | clicks to sign up vs. clicks to cancel, unsubscribe or delete (`paths[]`); `exit_channel` | leaving needs ≥ 3 more clicks, **or** works only by phone, chat or email |
| Buried controls | A | the leave/reject control's landmark (footer = `contentinfo`), accessibility-tree depth, font size, contrast, click depth | footer-only, or deep in the tree, or small low-contrast text |
| Interposed friction | A/B | number of interstitials in the leave path (survey, retention offer, repeated "are you sure") | each interstitial that adds a step without any required input counts as "unneeded" |

Decoys: a single confirmation dialog; a cancel button in the account menu as prominent as
Upgrade; a legally required notice step.

On real sites the walker measures discoverability only and stops before any final confirm.

### 3.4 Phase 9 modules
**Module 1, false urgency (built).** Two Tier A rules, measured by a probe: the first time a
page shows a clock or a stock count, the walker reads it again 2 s later on the same page,
and, if the clock ticked or a stock count is shown, reloads once.
- `urgency.countdown_reset`: after the reload the countdown shows more than 3 s more than a
  real clock allows (`excess_s = after - (before - elapsed)`).
- `urgency.stock_flux`: "only N left" is higher after the reload, with nothing bought.
A clock that does not tick in 2 s (opening hours, a timestamp) is never tested. The module
has its own 12-scenario grid (`tripwire eval --module urgency`); the v1 grid stays at 36.

**Still deferred:** nagging and forced registration, wire-level hidden fields, an LLM
confirm-shaming classifier, taint tracking, a browser extension, personalization probes,
regulatory mapping.

## 4. Data contracts

Pydantic models in `src/tripwire/schemas/`. Worked examples:
[`tests/fixtures/traces/`](../tests/fixtures/traces/) (one violating and one clean trace per
family) and [`tests/fixtures/findings/`](../tests/fixtures/findings/).

### 4.1 Rules for every schema
- Every file carries `schema_version`. Readers reject versions they do not know.
- Validated on write **and** on read. Unknown fields are errors.
- Money is `{"minor": <int>, "currency": "INR"}`: integer minor units, never floats. A float
  in a money field is a validation error, not a silent conversion.
- LLM spend is integer **micro-dollars** (D-005).
- Artifact paths are relative to the run folder. Timestamps are timezone-aware.
- Cross-references are checked: step indices, request ids, element ids, path names.

### 4.2 Trace
- **Header:** `run_id`, `site_url`, `site_type` (`shop`, `news`, `saas`, `other`), `mission`,
  `mode` (`sandbox` | `real`), `scenario_id`, `started_at`, `ended_at`, `status`,
  `budget_limits`, `budgets_used` (steps, wall seconds, page loads, LLM spend).
- **`steps[]`:** `index`, `timestamp`, `action` (`navigate`, `click`, `type`, `scroll`,
  `wait`, `reject_consent`, `handoff`) with its `target` (selector, role, accessible name,
  visible text), `url_before`, `url_after`, `page_load`, screenshot / accessibility / DOM
  snapshot paths, `requests[]` (the step's HAR slice, redacted), and:
  - `ui.elements[]`: role, text, bounding box, computed style (font size, colour,
    background, opacity, visible), contrast ratio, default state (`checked`, `selected`),
    `in_viewport`, `z_order`, `tree_depth`, `landmark`.
  - `overlays[]`: kind (banner, modal, interstitial), purpose (consent, newsletter,
    retention, survey, confirm), `layer`, bounding box, viewport coverage, whether it blocks
    interaction, and its controls (each pointing at a `ui.elements[]` entry and its styles).
  - `forms[]`: fields with type, label, default value, pre-checked, hidden, off-screen,
    required; and the submit control.
  - `timers[]`: text, pattern, seconds remaining, resets on reload.
- **`paths[]`:** measured journeys ("land → reject cookies"): goal, clicks, page loads,
  ordered step indices, `executed` (false = measured structurally), `completed`,
  `exit_channel` (web, phone, email, chat).
- **`intents[]`:** user goals tried (`reject_consent`, `unsubscribe`, `cancel`,
  `delete_account`), success flag, cheapest path found.
- **`commerce`** (only `reach_payment`): price ledger (label, amount, role, mandatory,
  first step seen), cart contents with `qty_added_by_walker`, default add-ons.
- **`notes[]`:** observations that are not findings: `page_instruction`, `handoff`,
  `safety_block`, `budget`, `info`.

### 4.3 Finding
`id`, `run_id`, `family`, `detector` (rule id), `tier`, `severity` (info < low < medium <
high), `confidence` (0–1, capped by tier), `mission`, `site_url`, `summary` (one plain
sentence), `evidence` (step indices, annotated screenshots, measured values, request ids),
`reproduce` (ordered steps with exact URLs), `taxonomy` (informational labels only, e.g.
Gray et al. 2018), `false_positive_notes`.

The schema rejects findings that claim a verdict or intent (illegal, scam, fraud, lying,
deliberately, intentional, ...), Tier A findings with no measured values, and confidence
above the tier cap.

## 5. Evaluation (summary)
36 sandbox scenarios = 3 families × 3 states (`clean` with decoys, `subtle`, `blatant`) ×
4 skins. Tier A targets: precision ≥ 0.95, recall ≥ 0.90, zero false positives on decoys,
exact click/page-load counts and price deltas, contrast within ±0.1. A hold-out (3 unseen
skins + 3 unseen layouts) is built last, never tuned against, and reported as the headline
(target precision ≥ 0.90, recall ≥ 0.80).

## 6. Out of scope for v1
- Any irreversible action on a real site: purchase, payment, account creation,
  subscription, deletion, message sending.
- Solving or bypassing CAPTCHAs, bot checks, logins or OTPs.
- Pages behind a login on real sites, unless it is a test account the owner holds and has
  approved for that run.
- Crawling beyond the URLs given and the per-run page-load budget.
- Mobile apps. Desktop web only.
- Phase 9 patterns (section 3.4).
- Any legal conclusion or claim about intent.

## 7. Open questions for the reviewer
1. Accept the contract additions in DECISIONS D-004 (mode, status, page_load, tree depth,
   landmark, overlay layer and purpose, executed and exit_channel on paths,
   `qty_added_by_walker`)?
2. Accept the tier confidence caps (B ≤ 0.75, C ≤ 0.4) in D-008?
3. Accept proposal P1 in the NOTEBOOK (every non-clean scenario plants every Tier A rule of
   its family) so each rule has 8 positives instead of 2–3?

## 8. Measurement definitions (Phase 2)

How the browser layer turns a page into the numbers above; details and trade-offs in DECISIONS
D-029.

| Quantity | Definition |
|---|---|
| contrast | WCAG 2.x ratio of the text colour composited over its composited background; `null` over images or gradients |
| area | bounding-box width × height in CSS pixels at a 1280×720 viewport |
| tree depth | number of semantic ancestors (landmarks, lists, forms, sections, dialogs, role-bearing elements) |
| landmark | nearest landmark ancestor; footer-only means `contentinfo` |
| overlay | visible fixed/sticky dialog or layer covering ≥ 5% of the viewport (headers and navs excluded) |
| blocks interaction | all 9 points of a 3×3 viewport grid land inside the overlay |
| page load | a main-frame `load` event during the step |
| click | one activated control (button, link, checkbox); typing is not a click |
