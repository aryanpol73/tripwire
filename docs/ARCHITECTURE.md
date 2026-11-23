# Architecture

Tripwire is a pipeline of small parts with one data contract between each pair. The browser
is used in one place only, the detectors never see it, and the report reads files.

```
missions/*.yaml        what to do on a site
      |
      v
Explorer (walker)      drives a real browser through the safety gate
  ScriptedWalker         role and visible-text rules (sandbox, Phase 3)
  LlmWalker              a model proposes, code checks, the gate decides (Phase 6)
      |
      v
Trace (trace.json)     every step: action, screenshot, a11y and DOM snapshot, UI inventory
                       (roles, boxes, computed styles, contrast), overlays, forms, requests,
                       measured paths, prices
      |
      v
Detectors              pure functions, Trace in, observations out; no browser, no network
      |
      v
Findings (findings.json)  tiered (A measured, B heuristic, C model-only), with evidence
      |
      v
Report (report.html)   one offline file a stranger can check in 30 seconds
```

## Where things live

| Path | What it does |
|---|---|
| `src/tripwire/mission.py`, `missions/` | Mission specs: goal, budgets, stop condition, applicable detectors |
| `src/tripwire/browser/session.py` | The only code that touches Playwright: throwaway profile, request routing, pacing, per-step capture |
| `src/tripwire/browser/safety_gate.py` | Rules in code, outside any model: allowlist, budgets, robots.txt, deny-lists for pay, delete, confirm and consent-accept |
| `src/tripwire/browser/ui_inventory.py`, `js/` | The in-page collector: every interactive element with role, name, box, style, WCAG contrast; overlays, forms, timers, prices |
| `src/tripwire/browser/redact.py` | Cookies, tokens, passwords and emails are removed before anything is saved |
| `src/tripwire/walker/base.py` | `ExplorerBase`: what both walkers share (session, gate, hand-offs, Trace assembly, real-site mode) |
| `src/tripwire/walker/scripted_walker.py`, `vocab.py` | The scripted walker and its small word list |
| `src/tripwire/llm/` | Observation, the six checked tools, prompts, decision sources (Anthropic, Groq, record, replay), completion, red-team audit |
| `src/tripwire/schemas/` | Pydantic models for Trace, Finding and ground truth; files are validated on read and write |
| `src/tripwire/detectors/` | The 11 v1 rules (`rules.py`), their code per family, and `thresholds.toml` |
| `src/tripwire/report/` | The HTML report builder, plain-language wording, and the text replay |
| `src/tripwire/eval/` | Scoring against ground truth, the hold-out contract, determinism fingerprints, the LLM eval |
| `src/tripwire/pilot/` | Phase 7: pre-flight, private labels, real-site runs and scoring |
| `sandbox/evilweb/` | The Evil Web sandbox: 3 site types x 3 families x 3 states x 4 skins = 36 scenarios with generated ground truth |
| `sandbox/redteam/`, `sandbox/unseen/` | 10 hostile pages and 3 unseen layouts for the LLM walker |

## Rules that hold everywhere

- **Safety is code, not prompt.** Every navigation, request and action goes through the gate.
  A model can propose; it cannot change the gate, the allowlist or the budgets.
- **Page content is data.** Anything read from a page reaches a model only inside a fenced,
  nonce-tagged block, and is never used as a typed value.
- **Detectors are pure.** They read a Trace and return observations, so they are tested in
  milliseconds on fixture traces and can be re-run on any saved run.
- **Every schema is versioned** and validated, and additive optional fields keep the version
  (D-011).
- **Findings are measurements.** Summaries pass a guard against verdict and intent words; the
  report states it is evidence, not a legal verdict.

## Why it is built this way

The reasoning, with the alternatives considered, is in [DECISIONS](DECISIONS.md); each
phase's results and mistakes are in the [NOTEBOOK](NOTEBOOK.md); the safety rules and where
each is enforced are in [ETHICS](ETHICS.md).
