"""WCAG contrast tests. Reference values from the WCAG 2.x definition and common tools."""

import pytest

from tripwire.browser.color import contrast_ratio, css_rgb, relative_luminance

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
