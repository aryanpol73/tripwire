"""WCAG contrast tests. Reference values from the WCAG 2.x definition and common tools."""

import pytest

from tripwire.browser.color import (
    contrast_ratio,
    css_rgb,
    effective_background,
    parse_css_color,
    relative_luminance,
    text_contrast,
)

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)


def test_luminance_extremes():
    assert relative_luminance(BLACK) == 0
    assert relative_luminance(WHITE) == pytest.approx(1.0)


def test_black_on_white_is_21():
    assert contrast_ratio(BLACK, WHITE) == pytest.approx(21.0)


def test_same_colour_is_1():
    assert contrast_ratio((120, 30, 200), (120, 30, 200)) == pytest.approx(1.0)


def test_order_does_not_matter():
    assert contrast_ratio(WHITE, (0, 82, 204)) == contrast_ratio((0, 82, 204), WHITE)


@pytest.mark.parametrize(
    ("fg", "bg", "expected"),
    [
        ((118, 118, 118), WHITE, 4.54),  # #767676: the classic "just passes AA" grey
        ((119, 119, 119), WHITE, 4.48),  # #777777: the classic "just fails AA" grey
        ((170, 170, 170), WHITE, 2.32),
        (WHITE, (0, 82, 204), 6.82),
    ],
)
def test_reference_pairs(fg, bg, expected):
    assert contrast_ratio(fg, bg) == pytest.approx(expected, abs=0.01)


def test_rejects_out_of_range_channels():
    with pytest.raises(ValueError):
        relative_luminance((256, 0, 0))


def test_css_rgb():
    assert css_rgb((0, 82, 204)) == "rgb(0, 82, 204)"


# --- Parsing computed colours and alpha compositing (Phase 2) ------------------------


@pytest.mark.parametrize(
    ("css", "expected"),
    [
        ("rgb(0, 82, 204)", (0, 82, 204, 1.0)),
        ("rgba(0, 0, 0, 0.5)", (0, 0, 0, 0.5)),
        ("rgb(0 82 204 / 50%)", (0, 82, 204, 0.5)),
        ("rgba(10, 20, 30, 0)", (10, 20, 30, 0.0)),
        ("transparent", (0, 0, 0, 0.0)),
        ("#fff", (255, 255, 255, 1.0)),
        ("#0052cc", (0, 82, 204, 1.0)),
        ("#00000080", (0, 0, 0, 128 / 255)),
    ],
)
def test_parse_css_color(css, expected):
    assert parse_css_color(css) == pytest.approx(expected)


@pytest.mark.parametrize("css", ["", "red", "linear-gradient(red, blue)", "rgb(1, 2)"])
def test_unparseable_colours_return_none(css):
    assert parse_css_color(css) is None


def test_transparent_layers_fall_through_to_the_canvas():
    layers = [(0, 0, 0, 0.0), (0, 0, 0, 0.0)]
    assert effective_background(layers) == pytest.approx((255, 255, 255))


def test_half_transparent_black_over_white_is_mid_grey():
    assert effective_background([(0, 0, 0, 0.5)]) == pytest.approx((127.5, 127.5, 127.5))


def test_innermost_opaque_layer_wins():
    # element (opaque blue) inside a red card inside the white page
    layers = [(0, 82, 204, 1.0), (255, 0, 0, 1.0)]
    assert effective_background(layers) == pytest.approx((0, 82, 204))


def test_text_contrast_matches_opaque_reference():
    white = (255, 255, 255, 1.0)
    assert text_contrast(white, [(0, 82, 204, 1.0)]) == pytest.approx(6.82, abs=0.01)


def test_semi_transparent_text_has_lower_contrast():
    faint = text_contrast((0, 0, 0, 0.4), [(255, 255, 255, 1.0)])
    assert 1.0 < faint < contrast_ratio(BLACK, WHITE)
    # black at 40% over white composites to rgb(153,153,153): 2.85:1
    assert faint == pytest.approx(2.85, abs=0.02)


def test_element_opacity_fades_the_text():
    full = text_contrast((0, 0, 0, 1.0), [(255, 255, 255, 1.0)])
    faded = text_contrast((0, 0, 0, 1.0), [(255, 255, 255, 1.0)], opacity=0.4)
    assert faded < full
