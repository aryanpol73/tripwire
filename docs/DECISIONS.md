# Decisions

One entry per decision: what we chose, the alternatives, and why. Newest at the bottom.
Entries marked **(needs approval)** add to or change what the kickoff brief specified.

---

### D-001 Stack as specified; heavy dependencies arrive with the phase that uses them
Python 3.12, uv, ruff, pytest, pre-commit, pydantic v2. Playwright, FastAPI, Jinja2 and
PyYAML are added in Phases 1–3.
**Why:** Playwright needs browser binaries. Installing them in CI before any code uses them
only slows CI and adds failure modes.

### D-002 hatchling as build backend; argparse for the CLI
**Alternatives:** uv_build or setuptools; Typer or Click.
**Why:** hatchling is stable and needs one line of config for a `src/` layout. argparse is in
the standard library and enough for a handful of subcommands ("no framework where a function
will do"). Both are easy to change later.

### D-003 pre-commit runs ruff through `uv run` (local hooks)
**Alternative:** the `ruff-pre-commit` hook repository with its own pinned version.
**Why:** with local hooks, the editor, pre-commit and CI all use the single ruff version
pinned in `uv.lock`. Two pins drift apart and produce "passes locally, fails in CI".

### D-004 Contract additions to the Trace **(needs approval)**
The brief's Trace is kept; these fields are added because a v1 rule or rule 1/6/10 needs them:

| Added | Needed by |
|---|---|
| `mode` (sandbox / real) | ETHICS rules 1, 6, 10 behave differently in the sandbox |
| `status`, `budget_limits` next to `budgets_used` | rule 8: a trace must show if it was cut short |
| `step.page_load` | page-load counts for click asymmetry and roach motel |
| `ui.elements[].tree_depth`, `landmark` | buried controls ("only in the footer, deep in the tree") |
| `ui.elements[].disabled` | decoy: a locked-on "strictly necessary" toggle is not a choice |
| `overlays[].layer`, `purpose` | "reject on the **first** layer"; telling consent banners from retention interstitials |
| `paths[].executed` | rule 6: the accept path is measured, not performed, on real sites |
| `paths[].exit_channel` | roach motel: "only works by phone, chat or email" |
| `commerce.cart[].qty_added_by_walker` | pre-added extras: compare with what the walker chose |
| `notes[].step_index`, `scenario_id`, `Target.role` | linking notes to steps; per-scenario eval; role-based locating |

### D-005 LLM spend is integer micro-dollars
**Alternatives:** cents (`Money` with USD); float dollars.
**Why:** one LLM call costs a fraction of a cent, so cents round it to zero, and floats are
banned for money. Micro-dollars are exact and still fit easily in an int.

### D-006 Money is a nested `{minor, currency}` object with a strict int
**Why:** one `Money` type is reused everywhere, so the no-float rule lives in one place.
`Strict()` is needed because pydantic's default lax mode silently turns `1499.0` into `1499`.

### D-007 The Trace validates its own cross-references
Step indices match positions; request ids are unique; overlay, form and timer element ids
exist in the same step; path steps exist and increase; intents name an existing path; a run
over budget must say so in `status`.
**Why:** detectors trust these links. Catching a broken link when the trace is written is far
cheaper than debugging a wrong finding later.

### D-008 Confidence caps per tier **(needs approval)**
Tier A ≤ 1.0, Tier B ≤ 0.75, Tier C ≤ 0.4, enforced by the Finding schema.
**Why:** the brief says Tier B is "medium" and Tier C "low" confidence, while `confidence` is
a 0–1 number. Without caps, a Tier C (LLM-only) finding could show 0.95 and look as solid as a
measurement. The exact cap values are a proposal; they are constants in one place.

### D-009 The Finding schema rejects verdict and intent words
illegal, unlawful, fraud(ulent), scam, lying, liar, cheat(ing), criminal, deliberate(ly),
intentional(ly), on purpose.
**Why:** ETHICS rule 7 and "no rule claims intent" are enforced in code, not left to wording
habits. The list is short and will grow if reviews find gaps.

### D-010 Tier A findings must carry measured values
**Why:** "detect by measuring" is the project's core promise. A Tier A finding without
numbers would be an opinion with a high-confidence label.

### D-011 Exact-match `schema_version`, no migrations yet
**Why:** there is no data in the wild to migrate. When a field changes we bump the version
and update the fixtures. Readers reject unknown versions loudly.

### D-012 Mission YAML files arrive in Phase 3
**Why:** the brief defines the mission spec format in Phase 3. Writing YAML now would mean
guessing the format, then rewriting it. `missions/README.md` describes the three missions until
then.

### D-013 LF line endings everywhere
`.gitattributes` forces LF and `write_model` writes LF.
**Why:** development is on Windows, CI is on Linux. Without this, the same JSON produces
different bytes on each OS and any byte-level comparison becomes noise.

---

## Phase 1

### D-014 Approved at the Phase 0 review
SPEC.md, the contract additions (D-004), the tier confidence caps (D-008) and proposals P1–P5
were approved on 2026-11-17.

### D-015 Site type alternates by skin
Odd skins run on a family's main site (consent → news, sneaking → shop, obstruction → saas),
even skins on its second site (saas, saas, news).
**Alternatives:** all 36 on the main site; secondary pages planted inside the main-site
scenarios.
**Why:** the brief asks for secondary placements and per-site-type reporting. With a fixed
3×3×4 grid, *something* must be confounded; here skin parity and site type are linked
(skins 2 and 4 are always the secondary site). The eval reports per skin and per site type
anyway, and NOTEBOOK records the confound.

### D-016 One family planted per scenario; other surfaces render their clean spec
**Why:** a scenario tests one family, while every other applicable rule must stay silent.
Those silent rules are extra negatives, which is what precision is measured on.

### D-017 Pages and ground truth are generated from the same Plan
**Alternative:** hand-write ground truth for each scenario.
**Why:** 36 hand-written files with exact paise and contrast values would drift from the
pages. Generating both from one Plan removes that class of error. The risk is a bug in the
Plan that both sides share; the browser smoke test and the user's click-through are the
independent check. A unit test fails if the committed ground truth differs from the
generated one.

### D-018 Measured controls carry their size and colours inline
**Why:** the visual-asymmetry, buried-control and renewal rules need exact area, font size and
contrast. Inline styles make the computed style equal to the spec, independent of the skin's
stylesheet. Checked in a real browser: computed width, height, font size and colours match.

### D-019 Rule catalog in `tripwire/detectors/rules.py`
**Why:** ground truth, detectors (Phase 4) and the eval refer to the same 11 rule ids. A typo
anywhere is caught by validation instead of silently scoring zero.

### D-020 "Applicable rules" depend on site and mission
For example, renewal disclosure exists only on the saas trial, and the shop has no leave flow.
Ground truth lists only rules that have something to measure. Result: 8 positives per Tier A
rule, except `sneaking.renewal_disclosure` with 4.

### D-021 In-memory, single-visitor server state with `POST /__reset`
**Alternative:** per-browser sessions.
**Why:** one scenario per server and one walker at a time. Simpler, and the reset endpoint
makes runs repeatable. The consent banner needs both the cookie and the server's own record,
because cookies ignore ports and a choice made on another scenario's server would otherwise
hide the banner.

### D-022 New dependencies: fastapi, jinja2, uvicorn, python-multipart; httpx (dev)
python-multipart is what FastAPI requires to parse HTML forms. Starlette's test client
warns that `httpx` support is deprecated in favour of a successor package; that package was
not added (unfamiliar name, possible typosquat). The warning is filtered in pytest config
until there is a reviewed replacement.

### D-023 A minimal WCAG contrast function now, alpha compositing in Phase 2
`tripwire/browser/color.py` computes contrast for opaque sRGB colours, tested against
reference pairs (#767676 on white = 4.54). The sandbox needs it to write exact ground truth.

---

## Phase 2

### D-024 Playwright sync API; a session can reuse an already-launched browser
**Alternative:** the async API.
**Why:** the walker is a simple loop, and sync code is easier to read and debug. Sessions take
an optional `browser`, but every session still gets its own fresh context (a throwaway
profile). Reusing Chromium makes the eval about 36× fewer browser launches.

### D-025 The allowlist restricts navigation; the sandbox blocks everything off-host
Accepted proposal P4. On real sites, sub-resources from other domains (for example a
consent-management script) load and are logged; only *navigation* off the allowlist is
blocked. In sandbox mode **every** off-host request is blocked, so a sandbox run is offline by
construction, not by convention.

### D-026 What the gate denies on real sites
- Irreversible controls, matched on the control's words: pay, purchase, place order, subscribe,
  start trial, create account, register, delete, confirm, "yes, I'm sure", send…
- Accept controls inside a consent overlay (ETHICS rule 6).
- Entering a leave flow (cancel, unsubscribe) unless the run is approved (rule 10).
- Non-GET requests to payment-like URLs and providers.
- In **every** mode: typing into password, card, OTP, UPI and similar fields.

The deny-list is deliberately broad. A false "no" costs a hand-off; a false "yes" could cost
money. The words are judged **before** touching the page, so a forbidden control is refused
even if it is missing or covered.

### D-027 Pacing: hard 2-second floor on real sites, configurable in the sandbox
`GateConfig` refuses `mode=real` with less than 2 s between actions. Sandbox tests use 0 s;
sandbox runs from the CLI will default to 2 s.

### D-028 HAR without response bodies, then scrubbed
`record_har_content="omit"`: page HTML contains tokens (the sandbox test found a CSRF token in
a saved HAR). After the context closes, cookies, auth headers, sensitive query and form values,
and email addresses are redacted in place. The per-step DOM snapshot is saved with hidden,
password and token-like input values blanked.

### D-029 Measurement definitions
- **Accessible name:** aria-labelledby, aria-label, `<label for>` or wrapping label (minus the
  control's own text), placeholder, then text content or title. A practical subset of the W3C
  accname algorithm; it handles the wrapped-label case the browser pane's own tree missed.
- **tree_depth:** number of *semantic* ancestors (landmarks, lists, forms, tables, sections,
  dialogs, elements with a role). Plain `<div>` wrappers do not count, so a skin's extra
  nesting does not make a control look "buried".
- **landmark:** nearest landmark ancestor; `<footer>`/`<header>` count only when not inside a
  sectioning element, as in ARIA.
- **z_order:** z-index of the nearest positioned ancestor with one; 0 otherwise.
- **contrast:** text colour composited over the background layers (element outward to the white
  canvas). The element's opacity is applied to the text only. Background images or gradients
  make contrast `None` (unmeasurable), and a rule then does not fire.
- **overlay:** a visible `position: fixed/sticky` element that is a dialog or covers ≥ 5% of
  the viewport; headers and navs are excluded. It **blocks interaction** when all 9 points of a
  3×3 grid over the viewport land inside it.

### D-030 Iframes and shadow DOM
Open shadow roots are walked. Every frame (cross-origin too) is measured and offset to page
coordinates; element ids are prefixed `f<n>`. An iframe that sits inside a main-frame overlay
contributes its controls to that overlay (the usual consent-management layout).

### D-031 A blocked click-navigation restores the previous page
Routing aborts the request, so nothing is sent, but Chromium then shows an error page. The
session navigates back to where it was and raises `SafetyBlocked`, so the walker keeps a usable
page and knows what happened.

### D-032 Price parser covers several currencies
INR, USD, EUR, GBP, JPY; Indian, Western and European number formats; signs, parentheses,
"Free", ranges and crossed-out or labelled old prices. Ambiguous text returns `None`.

### D-033 Local only: short virtualenv path on Windows
The project path in this session is long enough that Windows refused to load Playwright's
greenlet DLL ("filename too long"). Development used `UV_PROJECT_ENVIRONMENT` pointing to a
short path. This does not affect CI or a normal checkout location; README notes it.

---

## Phase 3

### D-034 Mission spec format
YAML in `missions/`: `name`, `goal`, `start_path`, `budgets` (the Trace `Budgets` model),
`stop` (`internal_pages` with a count, `left_or_blocked`, `before_payment`) and `detectors`
(validated against the rule catalog). Allowed domains are not in the file: they come from the
target URL at run time, so a mission cannot widen its own allowlist.
**Note:** `load_mission` reads from the repository's `missions/` folder; packaging the YAML
files into the wheel is a Phase 8 task.

### D-035 Trace schema 0.2.0: `commerce.terms`
Renewal and trial wording is plain text, not a control, so the UI inventory did not record it,
and a detector reads only the Trace. `TermsNotice` stores the text, font size, contrast, and
whether it mentions a price and a date. Version bumped; fixtures updated.

### D-036 Commerce is recorded whenever priced pages are seen
The brief scopes the commerce extension to `reach_payment`, but the saas trial (part of
`sign_up_and_leave`) carries the same sneaking patterns: setup fees at review, pre-selected
add-ons, renewal terms. The recorder runs on every step; `commerce` is null when no price,
cart, add-on or terms were seen.

### D-037 Paths are the cheapest chain found; detours stay in the trace
When the walker explores a link that leads nowhere (for example "Profile" while looking for
cancel), it goes back. Those steps remain in `steps[]`, but `paths[].step_indices` contains only
the chain that worked. Click counts therefore measure the route a user needs, not the walker's
search. The accept-consent path is never walked (rule 6): it is recorded as 1 click, 0 page
loads, `executed=false`, from the visible layer-1 accept control.

### D-038 Debt: the walker's English vocabulary
`walker/vocab.py` lists words such as "add to cart", "start trial", "cancel plan", "no thanks".
It is generic web vocabulary, not per-skin selectors, and it is the "tiny adapter" the brief
allows. Phase 6 should retire it. Known weaknesses: English only; "OK"/"Yes" are ambiguous;
an unusual wording for a leave link (for example "Manage membership") would be missed.

### D-039 Blocking pop-ups that are not the mission are closed
A newsletter modal on an article blocks clicks, as on real sites. In missions where the pop-up
is not the goal, the walker presses its Close or "No thanks" control. This click is not part
of any path; the pop-up itself is recorded in the step's overlays.

### D-040 Determinism is checked on a fingerprint of detector inputs
`tripwire.eval.fingerprint` hashes what detectors will read (actions, URL paths, page loads,
overlays with measured controls, forms, visible elements, paths, intents, commerce, notes) and
leaves out what may legitimately vary (timestamps, ports, request ids, wall time).

### D-041 Sandbox runs are not paced by default
`tripwire audit` uses a 0 s interval for the local sandbox (it is our own server). The
2-second floor for real sites is unchanged and enforced by `GateConfig`. Updates D-027.

### D-042 `audit` refuses real URLs until Phase 7
Any non-local host raises `RealSitesDisabled` before a browser starts.

### D-043 Price parser fix found by the walker
"Gift card sleeve × 1 ₹49" was read as ₹1: a currency sign right after a number was taken as
a suffix even when it began the next price. A suffix currency must now not be followed by a
digit. Regression test added.

### D-044 The budget check happens before each action
`BudgetTracker.check()` stops when another action would reach a limit (`>=`), so a finished
trace never shows more steps or page loads than allowed. LLM spend still uses `>`.

### D-045 Score rule decisions and measurement errors separately

Detectors consume the trace, the mission's applicable rules and the packaged threshold
configuration. They receive no scenario labels. The evaluator joins their output to the
committed ground truth by scenario and rule ID. A correct binary decision can still carry
an incorrect price or contrast. Either error is visible in the score. Undefined precision
or recall is reported as null. Tier B wording matches have their own scores.
The confidence values in findings encode the evidence tier and are uncalibrated.

### D-046 Freeze a development baseline and evaluate the hold-out independently

The CI reference contains measured precision and recall by group. A decrease greater than
0.02 fails the score check. Separately, the evaluator enforces each Tier A detector's targets
and checks the labeled measurements. Counts and minor currency units must match exactly.
Contrast has an absolute tolerance of 0.1. Grid path-load expectations follow the routes:
consent controls stay on the page, and the required acknowledgement in the SaaS leave flow
takes one click without a navigation.

The frontend team supplies the independent hold-out layouts, skins and labels after the
detectors are frozen. The evaluator accepts a live local fixture or a recorded sandbox trace.
The hold-out has its own aggregate Tier A gate and its own output directory.

### D-047 Record form structure and ambiguous evidence

The trace form inventory now records a visible alternative link within a form and the
boolean default of a hidden field when its literal value is recognizable as on or off.
Credential-like fields are excluded from boolean capture. The raw value follows the
existing redaction rules. Older traces load with false and unknown defaults for these
two optional observations. The finding set may now include `review_steps_by_rule`
for mixed consent wording or a hidden enabled field with unclear purpose. These steps
are outside the positive finding counts.

### D-048 Require labelled evidence for hidden opt-ins

An enabled hidden flag without a label goes to **needs review**, even when its
internal name suggests marketing or sharing. Record its step and exclude it from
the Tier A hidden opt-in count. Counting a hidden flag requires a label that
identifies an agreement. The v2 store label records the fixture author's intent.
The auditor reports only what the trace establishes.

### D-049 Lower confidence for ambiguous consent wording

A decline control containing both accept and reject cues is ambiguous. Send its
step for review. Mixed cues alone produce no wording finding. When the existing
confirmshaming rule independently fires on that text, assign confidence 0.50
instead of the usual Tier B value of 0.70. These are policy values, not calibrated
probabilities. The decision concerns wording only and applies after the frozen v2 run.

### D-050 One self-contained HTML report per run, rendered from the trace

`tripwire audit` writes `report.html` next to the trace; `tripwire report <run_dir>` rebuilds
it. The file has inline CSS, screenshots as data URIs and no scripts, so it opens offline,
survives email and cannot call home. Highlight boxes are absolutely positioned `<div>`s in
percentages of the PNG size read from its header, not boxes burned into the image: the
original screenshot stays untouched and the box can be checked against the trace bbox.
**Alternatives:** a PDF (heavier dependency, harder to diff), a small web app (needs a
server), drawing on the PNG with Pillow (alters the evidence, adds a dependency).

### D-051 Full-page screenshots

Steps now save `full_page=True` screenshots. A buried control is often in the footer, below
the first viewport; a viewport-only image could not show the evidence it is cited for. Trace
bounding boxes are already in page coordinates, so boxes line up without conversion. Cost:
larger PNGs on long pages. Detector inputs are unchanged, so fingerprints are unaffected.

### D-052 Report wording is built from measured values only

Each card leads with one plain sentence built from the finding's measurements (for example
"Joining took 3 clicks; leaving took 7 clicks"). The verdict-word guard that protects
finding summaries is applied to this wording in tests. Missing values are left out of the
sentence instead of printed as "None". A run with no findings never says "clean": it states
the mission, step count and status, and that unreached pages were not measured. Tier B and C
findings sit in a separate "Experimental" section; `review_steps_by_rule` gets its own
"Needs human review" table and never counts as a finding.

### D-011 amendment: additive optional fields keep the schema version

D-047 added optional fields (`FormField.hidden_boolean_default`, `Form.has_alternative_link`,
`FindingSet.review_steps_by_rule`) without bumping `schema_version`. That is now the rule:
a new optional field with a default that older files load correctly is additive and keeps
the version. Renaming, removing or changing the meaning or type of a field bumps it, and the
fixtures are updated in the same change.

### D-053 One Explorer base; the LLM walker only chooses actions

`walker/base.py` holds what both walkers share: the session, gate, budgets, capture,
hand-off detection, commerce recording and Trace assembly. `ScriptedWalker` and `LlmWalker`
implement only `_explore()`. The LLM walker acts through the same `click`, `type_into` and
`goto` helpers, so it cannot reach the browser any other way and produces the same Trace.
The scripted eval was re-run after the refactor with no change.

### D-054 The model proposes, code disposes

Six tools: click, type, scroll, navigate, handoff, done, all `strict` with closed schemas.
Before the gate, `llm/tools.check` refuses: ids not in the observation the model was shown,
invisible or disabled controls, clicking a consent accept control, typing into a field whose
name looks secret, typing into a non-text control, and anything but a same-site path for
navigate. The model never chooses typed text: the walker fills fields from test data by
label. A refusal is reported back to the model in the action history and counted.
**Alternatives:** trusting the gate alone (it does not know which ids the model saw, and in
the sandbox it allows irreversible clicks), letting the model write values (page text could
steer what is typed).

### D-055 Untrusted block with a random nonce; no host in the prompt

All page-derived text (path, title, control names, visible text) sits inside
`<untrusted_page_content_NONCE>`. The nonce is random per run and stored in the recording,
so a page cannot know it and replays rebuild identical prompts. The action history is
written by the walker from ids, tools, purposes and code-written outcomes only, never page
text. URLs appear as paths without host or port, which keeps prompts identical across
sandbox runs on random ports.

### D-056 One self-contained call per step

Each model call carries the system prompt, the mission, the last 15 walker-written history
lines and the current observation. No conversation history is resent, so cost per call is
flat, thinking blocks never need replaying, and each call can be recorded and replayed on
its own. The system prompt and tools are cached.

### D-057 Spend is enforced before the call, not after

Cost is computed from token usage and `llm/prices.toml` in integer micro-dollars (a US$ per
million tokens price is micro-dollars per token). Before each call the walker estimates its
worst case (the whole prompt written to the cache plus a full `max_tokens` of output) and
stops if that could pass the cap. An unknown model is refused unless a price is given, since
the cap could not be enforced. Every call is logged to `llm_calls.json`.
The LLM walker's wall-clock budget is four times the mission's, because model calls take
seconds where scripted steps take milliseconds; steps and page loads are unchanged.

### D-058 Completion is decided by code from the Trace

`llm/completion.py` judges a run the same way for both walkers: consent rejected if a banner
appeared, then enough internal pages (first_visit), a completed reach_payment path, or a
sign-up path plus a leave path that ended (left, or phone/email only). The model's `done`
claim is recorded but never counted. Paths are built from the purpose the model tags on each
action, so detours tagged `other` stay out of click counts.

### D-059 Unseen layouts declare their own end-state wording

The three unseen layouts use wording the scripted vocabulary does not know ("Reserve this
tour", "Count me in", "End membership"). Judging their leave flows with the sandbox's
"subscription cancelled" phrases would test the oracle, not the walker, so each layout
declares its own end-state text and pay control as ground truth (`RunRequest.left_text`,
`pay_control`). Caveat: the same person wrote the walker prompt and these layouts. The
prompt was frozen before the layouts were written and was not changed after running them.

### D-060 Red-team runs apply real-site action rules on the sandbox

`GateConfig.enforce_real_action_rules` makes the gate refuse pay, delete, confirm,
subscribe and consent-accept clicks on the local red-team pages, as it would on a real site.
`llm/redteam.audit` reads the finished Trace and counts violations (off-allowlist pages or
unblocked off-host requests, irreversible or accept clicks, typing into secret fields,
acting on the case's bait, any budget overrun). Refused or blocked attempts are reported
separately: they show the attack reached the model and code stopped it.

### D-061 Recorded decisions make LLM evals repeatable

Every live run writes `llm_decisions.jsonl` (nonce first, then one decision per call with
the request hash, usage and cost). `--replay-dir` plays them back with no network: the same
decisions, still checked against the page as it is now, with any changed prompt counted as
a divergence. Once a live eval is recorded, CI can replay it without an API key.

### D-062 Groq as a second model provider

The owner runs the live exit gate on Groq. `GroqSource` sits beside `AnthropicSource` behind
the same `Decision` interface, so the walker, the checks, the gate, the cap and
record/replay are unchanged; `TRIPWIRE_PROVIDER` picks one (or the only key present).
Groq's tool calling is OpenAI-compatible and its docs do not promise schema-strict
arguments, so unparseable arguments become an empty proposal that `tools.check` refuses, and
a call Groq itself rejects as malformed (`tool_use_failed`) is a refused proposal charged at
the worst-case cost. No caching discount is assumed. Only models with a public price on
Groq's models page are in `prices.toml` (`openai/gpt-oss-120b`, `openai/gpt-oss-20b`,
`qwen/qwen3.8-27b`); "contact sales" models such as the Llama ones are refused unless the
owner supplies a price. The kickoff brief named the Anthropic SDK; this is the owner's change.

### D-063 Fixes from the first live runs (Groq, openai/gpt-oss-120b)

The first live trials showed walker gaps, not model limits; each fix is generic:
re-read the page after a failed action (a late pop-up made observations stale); typing
counts as progress; text fields show "required" and "filled"; the walker states how many
different pages were opened, and marks links that "opened nothing" or "open a page you
already visited" (walker-observed navigation memory); the type check uses the gate's own
secret-field pattern (it had refused an Indian postal "PIN code"); on reach_payment a pay
control ends the mission and is refused, and completion counts any page after the cart that
showed one; the eval stops on a provider quota and `--resume` continues later.
Prompt size was trimmed (shorter tool schemas, page text only when it changed, 60 controls,
800 characters, 8 history lines): about 1,430 to 1,250 input tokens per call.
**Honest caveat:** the Streamly and Kettle unseen layouts were run during these trials, so
the fixes were informed by them. They are no longer strictly unseen; the final gate reports
them, but the Phase 7 real-site pilot is the clean generalisation test.

### D-064 Real-site mode needs a signed pre-flight, and has a local rehearsal

A non-local host is refused unless the run asks for `Mode.REAL` and
`private/pilot/preflight.yaml` exists, names the owner, is dated, and has every checklist
item set to true (Phases 4 to 6 targets met, sites chosen privately, flows labelled before
running, public pages only, findings private). The owner writes that file; the tool only
prints a template. `sign_up_and_leave` on a real site also needs `--approve-account-flows`
for that run (ETHICS 10). In real mode the walker loads robots.txt, paces actions at least
2 s apart, caps page loads at 30, and the gate applies every real-site action rule.
`Mode.REAL` on a local host is a rehearsal: the same rules, no pre-flight, so the mode is
tested end to end on the sandbox before any real site. **Alternatives:** a CLI flag alone
(too easy to pass by habit), an environment variable (invisible in the run record).

### D-065 Pilot labels are private and scored as Tier A precision

The owner's labels live in `private/pilot/labels.yaml` (git-ignored, with an `https` URL
per site alias). The scorer recomputes detector observations from each run's trace, so a
rule that did not fire still has its numbers compared with the label. Flows whose run did
not reach the measurement are "not measured": they neither help nor hurt precision and feed
the failure taxonomy, so a site that blocks the tool cannot inflate the score.

### D-066 Phase 9 modules get their own scenario grid

The v1 grid is generated from the families it lists (`scenarios.V1_FAMILIES`), not from the
`Family` enum, so adding a family never grows it. Each module has `module_grid(<module>)`:
3 states x 4 skins on its own site types, scored by `tripwire eval --module <name>` against
the per-detector targets and the decoy rule; the v1 baseline check applies only to the v1
grid. Module scenarios still measure every v1 rule on their pages (all must stay silent,
with exact numbers), and v1 scenarios render exactly as before (the module widget is absent).
**Why:** the v1 numbers, CI's baseline and the Phase 6 live-gate targets must not move
while a module is added. **Alternative:** one 48-scenario grid (changes every v1 result).

### D-067 False urgency is measured by a tick check and one reload

A countdown is tested only if it ticks: the walker reads the page, waits 2 s and reads it
again on the same page; if a clock went down (or a stock count is shown) it reloads once.
`countdown_reset` compares the reading after the reload with the reading before minus the
time between them, with a 3 s tolerance for capture jitter; `stock_flux` flags a count that
went up. **Why the tick check:** the v1 sandbox's phone-only cancel page says "10:00 to
16:00"; without it, opening hours would have been read as a countdown that "restarted".
Cost: one wait step on any page with a clock, plus one page load only for a live countdown
or a stock count, once per run.

### D-068 Module patterns are planted one at a time

The v1 planting rule says a planted scenario fires every Tier A rule of its family. The
urgency module plants its patterns separately (subtle: the countdown only; blatant: both),
so for `PER_PATTERN_FAMILIES` the ground-truth schema requires instead that a clean
scenario fires none of its family's rules and a planted one fires at least one; whether
each rule fires is read from the Plan's expected measurement. The v1 rule is unchanged.

### D-069 Compare the request body with the form measured just before submit

`wire.*` reads two things the trace already holds: the redacted POST body of the request a
submit click sent, and the form as measured on the step before that click (whose checkbox
state is the state at that moment, after any walker clicks). A visible checkbox measured
unticked but sent is a flipped choice; a field absent from the measured form but sent with a
yes-value is an injected opt-in. Security-style names (CSRF, nonce, token) are ignored and
other added fields go to review, because a field's purpose cannot be measured from its
value. Only url-encoded bodies matched to a measured form by method and action path count;
JSON calls and unknown bodies are out of scope. **Why:** a script can change a form at the
moment of submit, after every measurement of the page; the request is the only place it
shows. **Alternative:** watching DOM mutations at submit (needs page instrumentation and
still misses requests built without the form).
