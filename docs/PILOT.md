# Phase 7 pilot runbook

The pilot finds out where the sandbox lied. It runs the tool on 8 to 10 real sites that you
choose, compares it with flows you labelled by hand first, and records why it fails where it
fails. Everything about named sites stays on your machine.

## 0. Preconditions

- Phase 4 targets hold on the sandbox and the hold-out.
- Phase 5: two people verified report findings in under 30 seconds each.
- Phase 6: at least 85% mission completion on the sandbox and the unseen layouts, and 0
  violations on the red-team set, with the live model.

The tool refuses any non-local host until the pre-flight below is signed. ETHICS rules 1 to 10
apply in full: public pages only, at most 30 page loads per run, one action per 2 seconds,
robots.txt respected, never Accept, no irreversible action, a fresh browser profile.

## 1. Choose the sites (private)

Pick 8 to 10 public sites across at least four types: for example news, shop, SaaS pricing
and sign-up, travel or booking. Give each a neutral alias (`news-1`, `shop-2`). The real URL
appears only in `private/pilot/labels.yaml`, which git ignores.

## 2. Label 30 to 40 flows by hand, before any run

```powershell
uv run tripwire pilot labels > private/pilot/labels.yaml
```

Edit the file. For each flow write the site, the mission (`first_visit` or `reach_payment`;
`sign_up_and_leave` only on a test account you own), the rule, whether the pattern is present
in your judgement, and the numbers you counted (for example `accept_clicks: 1`,
`reject_clicks: 3`). Date each label. Label every flow before running the tool on that site,
so the tool cannot influence the labels.

```powershell
uv run tripwire pilot labels --check
```

## 3. Sign the pre-flight

```powershell
uv run tripwire pilot preflight > private/pilot/preflight.yaml
```

Fill in your name and the date and set each item to `true` only when it is true. The tool
never writes this file.

```powershell
uv run tripwire pilot preflight --check
```

## 4. Run

```powershell
uv run tripwire pilot run
uv run tripwire pilot run --walker llm
```

One run per labelled (site, mission), saved in `private/pilot/runs/<site>--<mission>/` with
its trace, findings and report. `--only news-1` reruns one site. Sign-up and leave flows also
need `--approve-account-flows`, for that run only, and only on your own test account.
If a site shows a CAPTCHA, a login wall or blocks the tool, the run stops and records it.
The tool never tries to get around it.

## 5. Score

```powershell
uv run tripwire pilot score
```

This compares each labelled flow with the detector result for that run and writes
`private/pilot/runs/score.json`. The gate is Tier A precision of at least 0.80 over the
measured flows. A flow whose run did not get that far (hand-off, block, error, no run) is
counted as not measured: it does not count for or against precision, it goes into the
failure taxonomy.

## 6. Failure taxonomy

For every miss, false positive and not-measured flow, write one line in
`private/pilot/failures.md`: the flow, what happened, and the class:

| Class | Example signs |
|---|---|
| Anti-bot wall | CAPTCHA, "verify you are human", a block page, run status `handed_off` or `blocked` |
| Consent-management iframe | the banner is in a cross-origin frame; no consent overlay found |
| Shadow DOM | controls missing from the inventory |
| Region-specific banner | a different or missing banner for this location |
| Page changes per visit | A/B tests, rotating promotions; counts differ between runs |
| Wording outside the vocabulary | the scripted walker misses a control the LLM walker finds |
| Measurement error | the rule fired, but the numbers disagree with the label |

Then fix the three largest classes only, and rerun.

## 7. Exit check

- Tier A precision of at least 0.80 on the hand-labelled flows.
- A written failure taxonomy.
- Zero rule violations.
- No site blocked the tool.

## 8. Disclosure

Findings on named sites stay private. If anything is ever published, anonymise the sites
or notify the owners privately first, with the report, and give them time to respond
(see ETHICS, Responsible disclosure). Describe findings as measurements, never accusations.
