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
