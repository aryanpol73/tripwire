# Tripwire hold-out v1

An independent test set for the Phase 4 detectors: **3 unseen skins × 3 unseen layouts**, with
expected results written by hand. Built after the detectors were frozen (Phase 4 merge,
`14c561a`), on its own branch, sharing no code or templates with `sandbox/evilweb`.

## How to run it (backend)

Run it **once**, with the detectors as they are, and report the numbers as the headline even if
they miss the target. If they miss, fix the measurement, never tune a threshold to this set
(kickoff brief, section 7).

```bash
uv run python -m holdout.serve
```

In a second terminal, while the servers are up:

```bash
uv run tripwire eval --holdout holdout/manifest.json
```

The servers listen on `127.0.0.1:8201`–`8209` only, use fake data, and load nothing from the
internet.

## Design

Each layout meets each skin once and each state once (a Latin square).

| Layout | Mission | Site type | Planted | dune | ocean | paper |
|---|---|---|---|---|---|---|
| grocery delivery | `reach_payment` | shop | sneaking | clean | subtle | blatant |
| video streaming | `sign_up_and_leave` | saas | obstruction + sneaking | blatant | clean | subtle |
| magazine | `first_visit` | news | consent | subtle | blatant | clean |

The consent banner is clean everywhere except the magazine.

| Skin | Theme | Banner | Class prefix | Accept (white on primary) | Body text | Muted |
|---|---|---|---|---|---|---|
| dune | warm light, rounded | floating card, bottom-left | `dn-` | 7.31 | 14.33 | 2.03 |
| ocean | dark blue, square | fixed bar across the top | `oc__` | 5.93 | 12.24 | 2.09 |
| paper | white, serif, no radius | centred modal with a dark backdrop (blocks the page) | `pp-` | 7.27 | 16.10 | 2.12 |

What is new compared with the development sandbox: a modal consent dialog with a backdrop, a
top bar and a floating card; layer-2 buttons in a different order from layer 1; prices in
`<table>` rows and a `<dl>` on the item page; a sidebar `<aside>` on every page; plans listed
side by side (the cheapest is not the chosen one); radio groups and fieldsets in forms; a
cancel entry behind a "Subscription" tab.

**Wording.** Controls use common English site wording ("Add to cart", "Start free trial",
"Cancel membership", "No thanks, cancel"). Unusual wording is left to the Phase 6 LLM explorer;
this set tests detectors on unseen pages, not the walker's vocabulary.

## How the expected values were derived

Typed by hand into `manifest.json` from the arithmetic below; not computed from the page code.
Afterwards every value was checked in a real browser with plain Playwright and
`getComputedStyle` (no Tripwire code): **all checks matched**. The walker, the detectors and
the eval were **not** run against this set.

Contrast: WCAG 2.x on opaque colours, rounded to 2 decimals.

### Consent

| Case | Reject clicks (accept = 1) | Reject on layer 1 | Compared layer | Area ratio | Accept / reject contrast | Fonts | Pre-selected | Fires |
|---|---|---|---|---|---|---|---|---|
| clean (any skin) | 1 | yes | 1 | 220×46 / 220×46 = 1.00 | equal | 15 / 15 | 0 | nothing |
| magazine-dune-subtle | 2 (Customise, Refuse all) | no | 2 | 300×50 / 160×32 = **2.93** | 7.31 / 14.33 | 16 / 14 | 1 | click, pre-selected; visual **not** (just under 3.0) |
| magazine-ocean-blatant | 2 (More options, reject) | no | 2 | 360×56 / 220×18 = 5.09 | 5.93 / 2.09 | 18 / 11 | 3 | click, visual, pre-selected; confirm-shaming (Tier B) |

The blatant decline text is "No thanks, I don't care about my privacy", which is new wording:
a correct Tier B detector should flag it.

### Grocery (₹, minor units = paise)

Item page: Bananas ₹45 + delivery ₹25 = **₹70 advertised total**.

| Case | Pre-ticked tip | Added for you | Late mandatory fees | Final total | Hidden / off-screen opt-ins |
|---|---|---|---|---|---|
| dune-clean | ₹20 offered, unchecked | none | none | 7000 | 0 (CSRF token and a visible "save address" box are decoys) |
| ocean-subtle | ₹10, pre-ticked | none | platform ₹4 → 400 | 4500+2500+1000+400 = **8400** | 1 off-screen, checked |
| paper-blatant | ₹30, pre-ticked | reusable bag ₹15 | small cart ₹30, platform ₹8, surge ₹12 → 5000 | 4500+1500+2500+3000+5000 = **16500** | 1 hidden `marketing_optin=1`, 1 off-screen |

Pre-added extras: subtle 1 (₹10 = 1000); blatant 2 (tip 3000 + bag 1500 = 4500).

### Streaming

Advertised: the default Standard plan, ₹299 per month (29900). Basic (₹149) is also listed, but it
is not the plan being bought. Final total = monthly total + one-time fees, as in the development
ground truth.

| Case | Pre-ticked extras | Late fees | Final total | Renewal disclosure before confirming | Opt-ins |
|---|---|---|---|---|---|
| ocean-clean | none | none | 29900 | date + price, 16 px, 12.24 | 0 |
| paper-subtle | 4K (+₹100) | activation ₹49 | 29900+10000+4900 = **44800** | date + price, **11 px, 2.12** | 1 |
| dune-blatant | 4K + extra screen (+₹50) | activation ₹99, service ₹20 | 29900+10000+5000+11900 = **56800** | **none** | 2 |

Joining is 3 clicks in every case (Start free trial, Continue, Activate trial; 3 page loads).

| Case | Leave path | Leave clicks | Extra vs. join | Ends | Entry control | Unneeded interstitials |
|---|---|---|---|---|---|---|
| ocean-clean | Cancel membership → Confirm cancellation | 2 | −1 | web | on the account page next to "Change plan", 15 px, 12.24 | 0 |
| paper-subtle | Subscription → footer link → survey → retention → confirm | 5 | 2 (**below 3**: roach motel does not fire) | web | footer only, 13 px, 16.10 | 2 |
| dune-blatant | Subscription → footer link → survey → retention → "Yes, I'm sure" | 5 | 2 | **phone** | footer only, 10 px, 2.03 | 3 |

## Coverage and caveats

- 9 cases, 54 expectations, 25 positives. Per rule the counts are small (1 to 3 positives), so
  a single miss moves a per-rule rate a lot; the gate is on overall Tier A.
- The same assistant built the development sandbox, so this set is not fully independent of
  its habits. New layouts, skins and hand-written values reduce that; the Phase 7 hand labels
  on real sites remain the truly independent test.
- Two near-threshold negatives are deliberate: the magazine-dune visual area ratio (2.93) and
  the streaming-paper leave cost (+2 clicks).
