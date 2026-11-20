"""The in-page collector against static HTML with tricky markup.

Reference contrast values are computed independently with the WCAG formula on the
composited colours (see the NOTEBOOK Phase 2 entry); the target is +-0.1.
"""

import pytest

from tests.browser.conftest import load_fixture
from tripwire.browser.ui_inventory import PageObservation, collect_page
from tripwire.schemas.trace import ControlPurpose, OverlayKind, OverlayPurpose


@pytest.fixture
def tricky(page) -> PageObservation:
    load_fixture(page, "tricky.html")
    return collect_page(page)


def by_name(obs: PageObservation, name: str):
    matches = [e for e in obs.elements if e.accessible_name == name]
    assert matches, f"no element named {name!r}; have {[e.accessible_name for e in obs.elements]}"
    return matches[0]


# --- accessible names ---------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["Work email", "Full name", "Coupon code", "Search the site", "PIN code", "Send me offers"],
)
def test_accessible_names_from_every_labelling_technique(tricky, name):
    by_name(tricky, name)


def test_wrapped_checkbox_is_named_by_its_label_not_its_value(tricky):
    box = by_name(tricky, "Send me offers")
    assert box.role == "checkbox"
    assert box.checked is True


# --- structure ------------------------------------------------------------------------


def test_tree_depth_ignores_plain_div_wrappers(tricky):
    assert by_name(tricky, "Deep in divs").tree_depth < by_name(tricky, "In a list").tree_depth


def test_footer_landmark(tricky):
    link = by_name(tricky, "Email preferences")
    assert link.landmark == "contentinfo"
    assert link.style.font_size_px == 10


def test_shadow_dom_is_traversed(tricky):
    assert by_name(tricky, "Shadow button").role == "button"


def test_iframe_contents_are_measured_with_page_coordinates(tricky):
    inside = by_name(tricky, "Inside frame")
    assert inside.id.startswith("f")
    assert inside.bbox.x >= 400 and inside.bbox.y >= 900


# --- visibility -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "name", ["Display none", "Visibility hidden", "Opacity zero", "Hidden attribute"]
)
def test_css_hidden_elements_are_marked_invisible(tricky, name):
    element = by_name(tricky, name)
    assert element.style.visible is False
    assert element.contrast_ratio is None


def test_visible_element_is_visible(tricky):
    assert by_name(tricky, "Opaque blue").style.visible is True


# --- contrast with alpha compositing ---------------------------------------------------


@pytest.mark.parametrize(
    ("name", "reference"),
    [
        ("Opaque blue", 6.821),  # white on rgb(0,82,204)
        ("Over half-black", 3.977),  # white on rgba(0,0,0,.5) over white = grey 127.5
        ("Faint text", 2.849),  # rgba(0,0,0,.4) over white = grey 153
    ],
)
def test_contrast_matches_reference_within_a_tenth(tricky, name, reference):
    assert by_name(tricky, name).contrast_ratio == pytest.approx(reference, abs=0.1)


def test_contrast_over_a_background_image_is_unmeasurable(tricky):
    assert by_name(tricky, "On a gradient").contrast_ratio is None


# --- overlays ---------------------------------------------------------------------------


def test_consent_banner_is_found_and_classified(tricky):
    banners = [o for o in tricky.overlays if o.purpose == OverlayPurpose.CONSENT]
    assert len(banners) == 1
    banner = banners[0]
    assert banner.kind == OverlayKind.BANNER
    assert banner.blocks_interaction is False
    purposes = {tricky.element(c.element_id).accessible_name: c.purpose for c in banner.controls}
    assert purposes == {
        "Accept all": ControlPurpose.ACCEPT,
        "Disagree": ControlPurpose.REJECT,  # not read as "agree"
        "Manage options": ControlPurpose.SETTINGS,
        "Save preferences": ControlPurpose.OTHER,
    }


def test_sticky_header_is_not_an_overlay(tricky):
    assert all(o.purpose == OverlayPurpose.CONSENT for o in tricky.overlays)


def test_modal_with_backdrop_blocks_interaction(page):
    load_fixture(page, "modal.html")
    obs = collect_page(page)
    assert len(obs.overlays) == 1
    modal = obs.overlays[0]
    assert (modal.kind, modal.purpose, modal.blocks_interaction) == (
        OverlayKind.MODAL,
        OverlayPurpose.NEWSLETTER,
        True,
    )
    assert modal.viewport_coverage == pytest.approx(1.0)


# --- forms, timers, prices -----------------------------------------------------------


def test_form_inventory(tricky):
    form = next(f for f in tricky.forms if f.action_url == "/signup")
    fields = {f.name: f for f in form.fields}
    assert fields["csrf_token"].hidden and fields["csrf_token"].default_value == "[REDACTED]"
    assert fields["partner_offers"].prechecked and fields["partner_offers"].off_screen
    assert fields["email"].required
    assert fields["seats"].default_value == "2"
    assert tricky.element(form.submit_element_id).accessible_name == "Create account"


def test_timers(tricky):
    found = {t.pattern: t for t in tricky.timers}
    assert found["mm:ss"].seconds_remaining == 599
    assert "only N left" in found


def test_sale_price_carries_the_crossed_out_price_beside_it(tricky):
    sale = [p for p in tricky.prices if p.parsed and p.parsed.minor == 149900]
    assert len(sale) == 1
    assert sale[0].struck == ["₹2,999"]


def test_price_labels_follow_semantic_rows_and_preserve_product_variants(page):
    from tripwire.walker.commerce import CommerceRecorder

    page.set_content("""
      <dl><dt>Delivery</dt><dd>£2</dd><dt>Total</dt><dd><em>£14</em></dd></dl>
      <table><tr><th>Filter (large) \u00d7 1</th><td>£12</td></tr>
        <tr><th>Total payable</th><td><b><span>£18</span></b></td></tr></table>
    """)
    recorder = CommerceRecorder()
    recorder.record_add("Filter (large)")
    recorder.observe(0, collect_page(page))
    commerce = recorder.build()
    assert [(line.label, line.amount.minor) for line in commerce.price_ledger] == [
        ("Delivery", 200),
        ("Total", 1400),
        ("Filter (large) \u00d7 1", 1200),
        ("Total payable", 1800),
    ]
    assert commerce.cart[0].qty_added_by_walker == 1
