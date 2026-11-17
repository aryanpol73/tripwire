# Missions

A mission is a named user journey: a goal, a stop condition, budgets and the detectors that
apply to it. The YAML format is defined in Phase 3; these three files arrive then:

| Mission | Journey | Detector families |
|---|---|---|
| `first_visit.yaml` | Land, handle any consent banner (reject path only on real sites), scroll, open 2–3 internal pages | consent asymmetry, obstruction |
| `sign_up_and_leave.yaml` | Find a sign-up, newsletter or trial, then find how to cancel, unsubscribe or delete | consent asymmetry, sneaking, obstruction |
| `reach_payment.yaml` | Add something to a cart or start a booking, go to the last page before payment | sneaking |

See [docs/SPEC.md](../docs/SPEC.md) section 2.
