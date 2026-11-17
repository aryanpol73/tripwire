"""Exit check for Phase 2: every sandbox page yields a valid Trace step, and what the browser
layer measures matches the ground truth the sandbox promised (contrast within +-0.1)."""

from datetime import UTC, datetime

import pytest

from evilweb import scenarios
from evilweb.ground_truth import build
from evilweb.plan import build_plan
from evilweb.server import serve
from tripwire.browser.capture import capture_step
from tripwire.schemas.trace import (
    Action,
    ActionKind,
    ControlPurpose,
    OverlayPurpose,
    SiteType,
    Step,
)

PAGES = {
    SiteType.SHOP: ["/", "/product/NOTE-03", "/cart", "/checkout/address", "/checkout/summary",
                    "/payment"],
    SiteType.NEWS: ["/", "/article/monsoon-markets", "/newsletter/leave/0", "/newsletter/thanks"],
    SiteType.SAAS: ["/", "/pricing", "/signup", "/signup/review", "/account", "/account/settings",
                    "/account/billing", "/account/cancel/0"],
}  # fmt: skip


def metric(truth, rule, key):
    return next(e.metrics[key] for e in truth.expectations if e.rule == rule)


def capture(page, tmp_path, index=0):
    return capture_step(
        page,
        index=index,
        action=Action(kind=ActionKind.NAVIGATE, value=page.url),
        url_before=None,
        page_load=True,
        run_dir=tmp_path,
        requests=[],
    )


@pytest.mark.parametrize("scenario_id", ["sneaking-blatant-skin1", "obstruction-subtle-skin2",
                                         "consent_asymmetry-blatant-skin2"])  # fmt: skip
def test_every_page_of_each_site_type_gives_a_valid_step(page, tmp_path, scenario_id):
    site = scenarios.get(scenario_id).site_type
    with serve(scenario_id) as url:
        for i, path in enumerate(PAGES[site]):
            page.goto(url + path)
            step, obs = capture(page, tmp_path, i)
            Step.model_validate(step.model_dump())  # round-trips through validation
            assert obs.elements, path


@pytest.mark.parametrize("scenario_id", [s.id for s in scenarios.grid()])
def test_consent_banner_measurements_match_ground_truth(page, tmp_path, scenario_id):
    truth = build(scenario_id)
    plan = build_plan(scenario_id)
    with serve(scenario_id) as url:
        page.goto(url + "/")
        page.wait_for_timeout(100)
        _, obs = capture(page, tmp_path)
    banners = [o for o in obs.overlays if o.purpose == OverlayPurpose.CONSENT]
    assert len(banners) == 1
    controls = {c.purpose: obs.element(c.element_id) for c in banners[0].controls}
    accept = controls[ControlPurpose.ACCEPT]
    first = plan.consent.layers[0]
    # The planned values are what ground truth is generated from (where the rule applies).
    assert accept.contrast_ratio == pytest.approx(first.accept.contrast, abs=0.1)
    if any(e.rule == "consent.visual_asymmetry" for e in truth.expectations):
        gt_accept = metric(truth, "consent.visual_asymmetry", "accept_contrast")
        assert accept.contrast_ratio == pytest.approx(gt_accept, abs=0.1)
    assert (accept.bbox.width, accept.bbox.height) == (first.accept.width, first.accept.height)
    assert accept.style.font_size_px == first.accept.font_px
    # Reject on layer 1 only in clean scenarios; otherwise it must not be offered there.
    assert (ControlPurpose.REJECT in controls) == (first.reject is not None)
    if first.reject is not None:
        reject = controls[ControlPurpose.REJECT]
        assert reject.contrast_ratio == pytest.approx(first.reject.contrast, abs=0.1)
        ratio = (accept.bbox.width * accept.bbox.height) / (reject.bbox.width * reject.bbox.height)
        assert ratio == pytest.approx(first.accept.area / first.reject.area, abs=0.01)


@pytest.mark.parametrize(
    "scenario_id",
    [s.id for s in scenarios.grid() if s.site_type != SiteType.SHOP],
)
def test_leave_entry_control_matches_ground_truth(page, tmp_path, scenario_id):
    truth = build(scenario_id)
    plan = build_plan(scenario_id)
    site = plan.scenario.site_type
    spec = plan.saas_leave if site == SiteType.SAAS else plan.news_leave
    path = "/" if site == SiteType.NEWS else ("/account/billing" if spec.pre_entry else "/account")
    with serve(scenario_id) as url:
        page.goto(url + path)
        _, obs = capture(page, tmp_path)
    entry = next(e for e in obs.elements if e.accessible_name == spec.entry.label)
    assert entry.contrast_ratio == pytest.approx(spec.entry.contrast, abs=0.1)
    assert entry.style.font_size_px == spec.entry.font_px
    assert (entry.landmark == "contentinfo") == (spec.entry_location == "footer")
    if any(e.rule == "obstruction.buried_control" for e in truth.expectations):
        assert entry.contrast_ratio == pytest.approx(
            metric(truth, "obstruction.buried_control", "contrast"), abs=0.1
        )


def test_pages_render_in_a_fixed_time(page, tmp_path):
    started = datetime.now(UTC)
    with serve("consent_asymmetry-clean-skin1") as url:
        page.goto(url + "/")
        capture(page, tmp_path)
    assert (datetime.now(UTC) - started).total_seconds() < 15
