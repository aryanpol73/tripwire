# Evil Web sandbox

Three small fake sites with planted dark patterns and known answers (ground truth). Fake data
only, no external network, served on `127.0.0.1` only.

| Site type | Pages | Families planted here |
|---|---|---|
| `shop/` | catalog, product, cart, address, summary, a fake payment page ("SANDBOX") | sneaking |
| `news/` | home, articles, consent banner, newsletter pop-up, newsletter leave flow | consent asymmetry, obstruction |
| `saas/` | landing, pricing, trial sign-up, review, account, settings, billing, cancel flow | consent asymmetry, sneaking, obstruction |

## Run it

```bash
uv run evilweb list
```

```bash
uv run evilweb serve consent_asymmetry-blatant-skin1
```

Then open <http://127.0.0.1:8100/>. To start the scenario over, restart the server or send
`POST /__reset`. Use `--port` to run several at once.

## How it is built

```
scenarios.py   the 36-scenario grid: {family, state, skin} -> site type and mission
skins.py       4 skins: theme, class/id prefix, nesting depth, button order, banner position, wording
patterns/      one module per family: {state, skin} -> exact values and expected metrics
plan.py        one scenario = skin + one spec per surface (only its own family is planted)
app.py         FastAPI app factory; shop/ news/ saas/ hold each site's routes and templates
ground_truth.py + ground_truth/   the expected answers, generated from the same plan
```

The pages and the ground truth read the same Plan, so they cannot disagree. Measured controls
(banner buttons, leave links, the renewal sentence) carry their exact size and colours inline.

| | clean (with decoys) | subtle (just past the threshold) | blatant (far past it) |
|---|---|---|---|
| consent | Accept = Reject on layer 1 | Reject on layer 2, area ratio 3.2, 1 toggle on | Reject on layer 3, tiny and faint, all toggles on, shaming text |
| sneaking (shop) | delivery shown up front | ₹9 late fee, ₹29 add-on pre-checked, 1 off-screen opt-in | ₹49 + ₹79 late fees, ₹99 add-on, an item added for you, hidden + off-screen opt-ins |
| sneaking (saas) | renewal shown clearly | ₹199 setup fee, support pre-checked, renewal in 11 px faint text | ₹499 + ₹49 fees, support + extra seat, no renewal date |
| obstruction (saas) | Cancel in the menu; notice + confirm (4 clicks) | footer-only link, survey, retention offer (6 clicks) | tiny footer link, 2x "are you sure", then phone only (7 clicks) |
| obstruction (news) | Newsletter in the header (3 clicks) | footer-only link, survey, retention offer (4 clicks) | tiny footer link, then email only (5 clicks) |

## Hand smoke test (Phase 1 exit check)

Click through at least one scenario per skin. What you should see:

| Scenario | Check |
|---|---|
| `consent_asymmetry-blatant-skin1` (news, bottom banner) | Layer 1 has a huge "Accept all" and a tiny grey "Manage options", no reject. Manage options opens toggles that are already on. "Legitimate interest" opens layer 3, where the reject reads "No thanks, I prefer a worse experience". Rejecting takes 3 clicks. |
| `sneaking-blatant-skin2` (saas, dark theme, centred banner) | Sign-up has 2 seats and priority support pre-selected and no renewal date. The review page adds a ₹499 setup fee and a ₹49 processing fee that the sign-up page never showed. |
| `obstruction-blatant-skin3` (saas, top banner) | The account page has Upgrade but no cancel. Account settings, then Billing and plan, then a tiny grey footer link, a survey, a 50%-off offer, two "are you sure" steps, and finally "please call". |
| `obstruction-subtle-skin4` (news, side banner) | No newsletter link in the header; "Email preferences" in the footer, then Leave newsletter, a survey and an offer, then done. |

Verified by Claude in a real browser on 2026-11-17 for these four. Your own click-through is
still the exit check.
