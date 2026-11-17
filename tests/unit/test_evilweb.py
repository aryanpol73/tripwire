"""Evil Web sandbox: the grid, the pages, the flows and the ground truth.

These tests use FastAPI's in-process test client: no browser and no network. They check
that every scenario renders and that the planted values on the pages match ground truth.
Measuring the pages the way a browser sees them is Phase 2's job.
"""

import json
import re
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from evilweb import scenarios
from evilweb.app import create_app
from evilweb.ground_truth import GROUND_TRUTH_DIR, build
from evilweb.patterns.common import format_inr
from evilweb.plan import build_plan
from evilweb.skins import SKINS
from tripwire.browser.color import contrast_ratio
from tripwire.schemas.ground_truth import GroundTruth, ScenarioState
from tripwire.schemas.trace import SiteType

GRID = scenarios.grid()
IDS = [s.id for s in GRID]

PAGES = {
    SiteType.SHOP: [
        "/",
        "/product/NOTE-03",
        "/cart",
        "/checkout/address",
        "/checkout/summary",
        "/payment",
    ],
    SiteType.NEWS: [
        "/",
        "/article/monsoon-markets",
        "/newsletter/leave/0",
        "/newsletter/thanks",
        "/newsletter/unsubscribed",
    ],
    SiteType.SAAS: [
        "/",
        "/pricing",
        "/signup",
        "/signup/review",
        "/account",
        "/account/settings",
        "/account/billing",
        "/account/cancel/0",
        "/account/cancelled",
    ],
}


def client(scenario_id: str) -> TestClient:
    return TestClient(create_app(scenario_id))


def gt(scenario_id: str) -> GroundTruth:
    return GroundTruth.model_validate_json(
        (GROUND_TRUTH_DIR / f"{scenario_id}.json").read_text(encoding="utf-8")
    )


def metric(truth: GroundTruth, rule: str, key: str):
    return next(e.metrics[key] for e in truth.expectations if e.rule == rule)


# --- Grid --------------------------------------------------------------------------


def test_grid_is_36_unique_scenarios():
    assert len(GRID) == 36
    assert len(set(IDS)) == 36
    assert Counter(s.family for s in GRID) == Counter({f: 12 for f in {s.family for s in GRID}})


def test_every_site_type_is_used_by_two_families():
    families_per_site = {}
    for s in GRID:
        families_per_site.setdefault(s.site_type, set()).add(s.family)
    assert {site: len(f) for site, f in families_per_site.items()} == {
        SiteType.NEWS: 2,
        SiteType.SAAS: 3,
        SiteType.SHOP: 1,
    }


def test_unknown_scenario_is_a_clear_error():
    with pytest.raises(KeyError, match="evilweb list"):
        scenarios.get("nope")


def test_skins_keep_their_contrast_promises():
    for skin in SKINS.values():
        p = skin.palette
        assert contrast_ratio(p.on_primary, p.primary) >= 4.5, skin.name
        assert contrast_ratio(p.muted, p.surface) < 3.0, skin.name
        assert contrast_ratio(p.text, p.surface) >= 4.5, skin.name


def test_skins_differ_in_class_prefix_and_wording():
    assert len({s.prefix for s in SKINS.values()}) == 4
    assert len({s.w("reject") for s in SKINS.values()}) == 4
    assert len({s.nesting for s in SKINS.values()}) == 4


# --- Ground truth ------------------------------------------------------------------


@pytest.mark.parametrize("scenario_id", IDS)
def test_committed_ground_truth_is_valid_and_current(scenario_id):
    # If this fails after changing a pattern, run: uv run evilweb ground-truth
    assert gt(scenario_id) == build(scenario_id)


def test_ground_truth_folder_has_exactly_the_grid():
    assert sorted(p.stem for p in GROUND_TRUTH_DIR.glob("*.json")) == sorted(IDS)


def test_every_tier_a_rule_has_positives_and_negatives():
    fired, silent = Counter(), Counter()
    for sid in IDS:
        for e in gt(sid).expectations:
            if e.tier == "A":
                (fired if e.should_fire else silent)[e.rule] += 1
    for rule in silent:
        assert fired[rule] >= 4, f"{rule} has only {fired[rule]} positives"
        assert silent[rule] >= 4, f"{rule} has only {silent[rule]} negatives"


def test_clean_scenarios_fire_nothing_and_list_decoys():
    for s in GRID:
        if s.state == ScenarioState.CLEAN:
            truth = gt(s.id)
            assert not any(e.should_fire for e in truth.expectations)
            assert truth.decoys


# --- Pages render, offline ---------------------------------------------------------

EXTERNAL = re.compile(r"""(src|href|action)\s*=\s*["']?(https?:)?//""", re.IGNORECASE)


@pytest.mark.parametrize("scenario_id", IDS)
def test_every_page_renders_without_external_resources(scenario_id):
    c = client(scenario_id)
    site = scenarios.get(scenario_id).site_type
    for path in [*PAGES[site], "/about", "/privacy"]:
        r = c.get(path)
        assert r.status_code == 200, path
        assert "<html" in r.text
        assert not EXTERNAL.search(r.text), f"{path} references an external resource"


@pytest.mark.parametrize("scenario_id", IDS)
def test_consent_banner_shows_until_a_choice_is_made(scenario_id):
    c = client(scenario_id)
    assert 'aria-label="Cookie consent"' in c.get("/").text
    r = c.post("/consent", json={"choice": "reject", "toggles": {}})
    assert r.status_code == 204
    assert 'aria-label="Cookie consent"' not in c.get("/").text


@pytest.mark.parametrize("scenario_id", IDS)
def test_banner_renders_the_planned_layers_and_controls(scenario_id):
    plan = build_plan(scenario_id)
    html = client(scenario_id).get("/").text
    assert html.count("data-layer=") == len(plan.consent.layers)
    for layer in plan.consent.layers:
        assert layer.accept.style in html
        if layer.reject:
            assert layer.reject.style in html


def test_reset_starts_over():
    c = client("sneaking-blatant-skin1")
    c.post("/cart/add", data={"sku": "NOTE-03"})
    assert "Cart (2)" in c.get("/").text  # one chosen, one sneaked in
    c.post("/__reset")
    assert "Cart (0)" in c.get("/").text


# --- Flows match ground truth -------------------------------------------------------


@pytest.mark.parametrize("scenario_id", [s.id for s in GRID if s.site_type == SiteType.SHOP])
def test_shop_checkout_totals_match_ground_truth(scenario_id):
    truth = gt(scenario_id)
    c = client(scenario_id)
    c.post("/cart/add", data={"sku": "NOTE-03"})
    c.post("/checkout/address", data={"name": "Test", "phone": "0", "pincode": "1", "city": "X"})
    summary = c.get("/checkout/summary").text
    final = metric(truth, "sneaking.price_drift", "final_total_minor")
    assert f"Total payable</span><span>{format_inr(final)}" in summary
    assert "SANDBOX" in c.get("/payment").text


@pytest.mark.parametrize("scenario_id", [s.id for s in GRID if s.site_type == SiteType.SAAS])
def test_saas_trial_review_matches_ground_truth(scenario_id):
    truth = gt(scenario_id)
    plan = build_plan(scenario_id)
    c = client(scenario_id)
    form = {"email": "walker@example.test", "seats": str(plan.saas_trial.default_seats)}
    if plan.saas_trial.support_preselected:
        form["support"] = "1"
    c.post("/signup", data=form)
    review = c.get("/signup/review").text
    final = metric(truth, "sneaking.price_drift", "final_total_minor")
    drift = metric(truth, "sneaking.price_drift", "drift_from_mandatory_minor")
    assert f"Monthly total</span><span>{format_inr(final - drift)}" in review
    for fee in plan.saas_trial.late_fees:
        assert fee.label in review
        assert fee.label not in c.get("/signup").text  # fees appear only at review
    assert (plan.saas_trial.renewal is not None) == ("per month from" in review)


def _walk_leave(c: TestClient, base: str, steps) -> str:
    """Click through a leave flow; return the final page."""
    page = ""
    for index, kind in enumerate(steps):
        page = c.get(f"{base}/{index}").text
        if kind in ("phone_only", "email_only"):
            return page
        data = {"acknowledge": "1"} if kind == "notice" else {}
        r = c.post(f"{base}/{index}", data=data)
        page = r.text
    return page


@pytest.mark.parametrize("scenario_id", IDS)
def test_leave_flow_ends_as_planned(scenario_id):
    plan = build_plan(scenario_id)
    site = plan.scenario.site_type
    if site == SiteType.SHOP:
        pytest.skip("the shop has no leave flow")
    spec = plan.saas_leave if site == SiteType.SAAS else plan.news_leave
    base = "/account/cancel" if site == SiteType.SAAS else "/newsletter/leave"
    final = _walk_leave(client(scenario_id), base, spec.steps)
    if spec.exit_channel == "phone":
        assert "please call" in final
    elif spec.exit_channel == "email":
        assert "send an email" in final
    else:
        assert "cancelled" in final.lower() or "left the newsletter" in final


@pytest.mark.parametrize("scenario_id", IDS)
def test_leave_entry_is_where_ground_truth_says(scenario_id):
    plan = build_plan(scenario_id)
    site = plan.scenario.site_type
    if site == SiteType.SHOP:
        pytest.skip("the shop has no leave flow")
    spec = plan.saas_leave if site == SiteType.SAAS else plan.news_leave
    c = client(scenario_id)
    page = c.get(
        "/account/billing"
        if site == SiteType.SAAS and spec.pre_entry
        else "/account"
        if site == SiteType.SAAS
        else "/"
    ).text
    footer = page.split("<footer", 1)[1]
    assert (spec.entry.style in footer) == (spec.entry_location == "footer")
    assert spec.entry.style in page


def test_ground_truth_files_are_lf_json():
    raw = (GROUND_TRUTH_DIR / f"{IDS[0]}.json").read_bytes()
    assert b"\r\n" not in raw
    json.loads(raw)


def test_banner_returns_after_reset_even_with_an_old_cookie():
    # Cookies ignore ports: a choice made on another scenario's server must not hide this one.
    c = client("consent_asymmetry-clean-skin1")
    c.post("/consent", json={"choice": "reject", "toggles": {}})
    c.post("/__reset")
    assert 'aria-label="Cookie consent"' in c.get("/").text


@pytest.mark.parametrize("skin", [1, 2, 3, 4])
def test_stylesheet_is_not_html_escaped(skin):
    # Browsers do not decode entities inside <style>; an escaped quote drops the rule.
    html = client(f"consent_asymmetry-clean-skin{skin}").get("/").text
    style = html.split("<style>", 1)[1].split("</style>", 1)[0]
    assert "&#39;" not in style and "&quot;" not in style
    assert SKINS[skin].font in style
