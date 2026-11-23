"""Generate ground_truth.json for every scenario from its Plan.

Run `uv run evilweb ground-truth` after changing a pattern. A unit test fails if the
committed files differ from what this module generates.
"""

from __future__ import annotations

from pathlib import Path

from evilweb import scenarios
from evilweb.patterns import consent, obstruction, sneaking, urgency
from evilweb.plan import Plan, build_plan
from tripwire.detectors.rules import RULES
from tripwire.schemas.finding import Family, Tier
from tripwire.schemas.ground_truth import GroundTruth, RuleExpectation, ScenarioState
from tripwire.schemas.io import write_model
from tripwire.schemas.trace import SiteType

GROUND_TRUTH_DIR = Path(__file__).parent / "ground_truth"

_CONSENT = [r for r in RULES if r.startswith("consent.")]
_OBSTRUCTION = [r for r in RULES if r.startswith("obstruction.")]
_SHOP_SNEAKING = ["sneaking.price_drift", "sneaking.preadded_extras", "sneaking.bundled_optins"]
_SAAS_SNEAKING = [*_SHOP_SNEAKING, "sneaking.renewal_disclosure"]
_URGENCY = [r for r in RULES if r.startswith("urgency.")]

# Which rules have something to measure for a given site and mission.
APPLICABLE: dict[tuple[SiteType, str], list[str]] = {
    (SiteType.NEWS, "first_visit"): _CONSENT,
    (SiteType.NEWS, "sign_up_and_leave"): _CONSENT + _OBSTRUCTION,
    (SiteType.SHOP, "reach_payment"): _SHOP_SNEAKING,
    (SiteType.SAAS, "sign_up_and_leave"): _CONSENT + _SAAS_SNEAKING + _OBSTRUCTION,
}

NOTES = [
    "Clicks count activated controls (buttons, links, checkboxes); typing is not a click.",
    "Money is integer paise (INR). Contrast ratios are WCAG 2.x, rounded to 2 decimals.",
    "reach_payment adds the cheapest item (NOTE-03, qty 1) and stops before payment.",
    "sign_up joins from the landing page; leave_clicks start on the account or home page.",
]


def _all_metrics(plan: Plan) -> dict[str, dict]:
    site = plan.scenario.site_type
    found = plan.consent.metrics(site)
    found |= plan.shop.metrics() if site == SiteType.SHOP else plan.saas_trial.metrics()
    leave = plan.saas_leave if site == SiteType.SAAS else plan.news_leave
    return found | leave.metrics() | plan.urgency.metrics()


def _decoys(plan: Plan, applicable: list[str]):
    site = plan.scenario.site_type
    found = consent.decoys(plan.consent)
    found += (
        sneaking.shop_decoys(plan.shop)
        if site == SiteType.SHOP
        else sneaking.saas_decoys(plan.saas_trial)
    )
    found += obstruction.decoys(plan.saas_leave if site == SiteType.SAAS else plan.news_leave)
    found += urgency.decoys(plan.urgency)
    # Keep decoys whose guarded rules are measured here; drop guards for rules that are not.
    kept = []
    for decoy in found:
        guards = [r for r in decoy.must_not_trigger if r in applicable]
        if guards:
            kept.append(decoy.model_copy(update={"must_not_trigger": guards}))
    return kept


def build(scenario_id: str) -> GroundTruth:
    plan = build_plan(scenario_id)
    sc = plan.scenario
    applicable = APPLICABLE[(sc.site_type, sc.mission)]
    if sc.family == Family.URGENCY:  # module scenarios also measure the urgency rules
        applicable = applicable + _URGENCY
    metrics = _all_metrics(plan)
    planted = sc.state != ScenarioState.CLEAN

    expectations = []
    for rule_id in applicable:
        rule = RULES[rule_id]
        own = rule.family == sc.family
        if rule.family == Family.URGENCY:
            # Each urgency pattern is planted on its own (subtle: the countdown only), so
            # read whether it fires from the Plan's own expected measurement.
            m = metrics.get(rule_id, {})
            fires = own and bool(m.get("timer_restarted") or m.get("stock_went_up"))
        elif rule.tier == Tier.A:
            fires = own and planted
        else:  # Tier B: confirm-shaming wording is planted only in blatant consent scenarios
            fires = own and sc.family == Family.CONSENT_ASYMMETRY and plan.consent.shaming
        expectations.append(
            RuleExpectation(
                rule=rule_id,
                family=rule.family,
                tier=rule.tier,
                should_fire=fires,
                metrics=metrics[rule_id],
            )
        )
    return GroundTruth(
        scenario_id=sc.id,
        family=sc.family,
        state=sc.state,
        skin=sc.skin,
        site_type=sc.site_type,
        mission=sc.mission,
        expectations=expectations,
        decoys=_decoys(plan, applicable),
        notes=NOTES,
    )


def write_all(out_dir: Path = GROUND_TRUTH_DIR) -> list[Path]:
    return [write_model(build(s.id), out_dir / f"{s.id}.json") for s in scenarios.every_scenario()]
