# Tripwire hold-out v2

A second independent test set, built after the Phase 4 measurement fixes
(`phase-4-measurement-fixes` at `dbc41b4`) to check whether those fixes generalise. `holdout/v1`
cannot do that: it was scored once and the fixes were made after seeing its failures.

**3 more unseen skins × 3 more unseen layouts**, expected values written by hand. No code or
templates shared with `sandbox/evilweb` or `holdout/` (v1). This branch is based on the fixes
branch, so it runs the code under test as-is.

## How to run it (backend)

Run it **once**, with the detectors exactly as on `dbc41b4`. Report the numbers as the
headline even if they miss (Tier A precision ≥ 0.90, recall ≥ 0.80). If anything misses,
fix the measurement and record it; never tune a threshold or a pattern to these pages.

```bash
uv run python -m holdout2.serve
```

In a second terminal:

```bash
uv run tripwire eval --holdout holdout2/manifest.json
```

Servers listen on `127.0.0.1:8301`–`8309` only, fake data, nothing loaded from the internet.

## Design

| Layout | Mission | Site type | Planted | forest | candy | mono |
|---|---|---|---|---|---|---|
| electronics store | `reach_payment` | shop | sneaking | clean | subtle | blatant |
| online courses | `sign_up_and_leave` | saas | obstruction + sneaking | blatant | clean | subtle |
| community forum | `first_visit` | news | consent | subtle | blatant | clean |

| Skin | Theme | Banner | Prefix | Accept | Body text | Muted |
|---|---|---|---|---|---|---|
| forest | dark green | left drawer, full height | `fr_` | 5.02 | 12.77 | 2.29 |
| candy | pink, very rounded | bottom sheet, full width | `cy-` | 6.04 | 15.79 | 1.90 |
| mono | black on white, no radius | small toast, top right | `mo-k-` | 21.00 | 20.12 | 2.28 |

**Chosen to test the Phase 4 fixes on different markup:**

| Fix in `dbc41b4` | What v2 does differently |
|---|---|
| two-cell table rows and `<dt>`/`<dd>` pairs | prices in `<div>` rows with two `<span>`s; the cart is a **3-column** table (Item, Qty, Price); summary lines say "USB-C cable (1)" instead of "× 1" |
| the chosen plan comes from a pre-checked radio | the plan is chosen by a **button on a plan card**; the sign-up form shows the plan as text, no radio; Basic (₹199) is cheaper than the chosen Pro (₹499) |
| bracketed text kept in item names | items have no bracketed size; the quantity is in brackets on the summary instead |
| "No thanks" next to "Accept offer" counts as a retention step | the offer is "Pause my plan" next to "Continue cancelling"; no "no thanks" and no "% off" |
| radio survey counts as friction | the survey uses **checkboxes** and a "Next" button |
| shaming regex "I don't care about / value my ___" | the shaming text is "Decline and accept a worse experience" |

Also new: cookie settings expand **inside** the same banner (layer-1 buttons stay visible), a
leave link that is buried by **size and contrast in the page body** rather than the footer, an
**email-only** exit, and total labels "Estimated total", "Cart total", "Order total".

Wording stays within common English site conventions; vocabulary generalisation is the
Phase 6 explorer's job.

## Expected values (typed by hand, then checked)

Checked afterwards in a real browser with plain Playwright and `getComputedStyle`, no
Tripwire code: **all checks matched**. The walker, detectors and eval were **not** run.

### Consent (forum)

| Case | Reject clicks | Reject on layer 1 | Layer | Area ratio | Accept / reject contrast | Fonts | Pre-selected | Fires |
|---|---|---|---|---|---|---|---|---|
| clean (also on every courses case) | 1 | yes | 1 | 200×44 / 200×44 = 1.00 | equal | 15 / 15 | 0 | nothing |
| forum-forest-subtle | 2 | no | 2 | 280×48 / 170×34 = **2.33** | 5.02 / 12.77 | 16 / 14 | 2 | click, pre-selected; visual **not** |
| forum-candy-blatant | 2 | no | 2 | 340×54 / 240×18 = 4.25 | 6.04 / 1.90 | 18 / 11 | 3 | click, visual, pre-selected, confirm-shaming (B) |

### Store (paise)

Product page: USB-C cable 29900 + delivery 4900 = **34800 estimated total**.

| Case | Pre-ticked care plan | Added for you | Late mandatory fees | Final | Opt-ins |
|---|---|---|---|---|---|
| forest-clean | ₹99 offered, unchecked | none | none | 34800 | 0 |
| candy-subtle | ₹99 pre-ticked | none | convenience 1900 | 29900+4900+9900+1900 = **46600** | 1 off-screen |
| mono-blatant | ₹149 pre-ticked | cable organiser ₹79 | packaging 2500, payment handling 3000 | 29900+7900+4900+14900+5500 = **63100** | 1 hidden `promo_emails=1`, 1 off-screen |

Pre-added: subtle 1 (9900); blatant 2 (14900 + 7900 = 22800).

### Courses

Advertised: Pro, 49900 per month. Joining: Start free trial, Continue, Begin trial (3 clicks,
3 page loads). Final total = monthly total + one-time fees.

| Case | Pre-ticked extras | Late fees | Final | Renewal before confirming | Opt-ins |
|---|---|---|---|---|---|
| candy-clean | none | none | 49900 | price + date, 16 px, 15.79 | 0 |
| mono-subtle | certificates +15000 | onboarding 9900 | **74800** | price + date, **10 px, 2.28** | 1 |
| forest-blatant | certificates + mentor (+40000) | onboarding 19900, platform 4900 | **114700** | **none** | 2 |

| Case | Leave path | Clicks | Extra | Ends | Entry | Unneeded steps |
|---|---|---|---|---|---|---|
| candy-clean | Cancel subscription → Yes, cancel | 2 | −1 | web | account page next to "Change plan", 14 px, 15.79 | 0 |
| mono-subtle | Billing → cancel link → survey → pause offer → Yes, cancel | 5 | 2 (**below 3**) | web | page body, **11 px, 2.28**, not footer | 2 |
| forest-blatant | Billing → footer link → survey → pause offer → Yes, I'm sure | 5 | 2 | **email** | footer, 10 px, 2.29 | 3 |

## Caveats

- 9 cases, 54 expectations, 25 positives; per-rule counts are small.
- Two deliberate near-threshold negatives again: forum-forest visual ratio 2.33 and
  courses-mono leave cost +2.
- Same author as the sandbox and v1; the Phase 7 hand labels remain the truly independent test.
