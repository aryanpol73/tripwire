# Evil Web sandbox

Three small fake sites with planted dark patterns and known answers (ground truth). Built
in Phase 1. Fake data only, no external network.

| Site type | Pages | Families planted here |
|---|---|---|
| `shop/` | catalog, product, cart, checkout | sneaking |
| `news/` | articles, consent banner, newsletter pop-up | consent asymmetry, obstruction (newsletter unsubscribe) |
| `saas/` | landing, pricing and trial sign-up, account settings, cancel or delete flow | obstruction, sneaking (trial page), consent asymmetry (sign-up page) |

Scenario grid: 3 families × 3 states (`clean` with decoys, `subtle`, `blatant`) × 4 skins
= 36 scenarios, each with a `ground_truth.json`.
