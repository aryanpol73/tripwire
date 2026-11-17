"""Price parser: visible price text -> integer minor units. Tests written before the code."""

import pytest

from tripwire.browser.price_parse import find_amounts, parse_price

NBSP = "\u00a0"
NNBSP = "\u202f"  # narrow no-break space, used by French formatting
MINUS = "\u2212"
EN_DASH = "\u2013"
TIMES = "\u00d7"  # multiplication sign, as in "x 2"


@pytest.mark.parametrize(
    ("text", "minor", "currency"),
    [
        # Indian rupee spellings
        ("₹1,499", 149900, "INR"),
        ("₹ 1,499", 149900, "INR"),
        ("Rs. 499", 49900, "INR"),
        ("Rs.499/-", 49900, "INR"),
        ("INR 1,499.00", 149900, "INR"),
        ("1,499 INR", 149900, "INR"),
        # Indian digit grouping
        ("₹1,23,456.50", 12345650, "INR"),
        ("₹10,00,000", 100000000, "INR"),
        # US dollar
        ("$1,234.56", 123456, "USD"),
        ("US$ 20", 2000, "USD"),
        ("USD 1,000", 100000, "USD"),
        ("$19.9", 1990, "USD"),
        # Euro with decimal comma and dot or space grouping
        ("1.234,56 €", 123456, "EUR"),
        ("€ 9,99", 999, "EUR"),
        (f"1{NNBSP}234,56{NBSP}€", 123456, "EUR"),
        ("EUR 1.000", 100000, "EUR"),
        # Pound and yen (yen has no minor unit)
        ("£12.50", 1250, "GBP"),
        ("¥1,200", 1200, "JPY"),
        # per-period suffixes do not change the amount
        ("₹799/month", 79900, "INR"),
        ("$12 per month", 1200, "USD"),
    ],
)
def test_amounts(text, minor, currency):
    parsed = parse_price(text)
    assert parsed is not None, text
    assert (parsed.kind, parsed.minor, parsed.currency) == ("amount", minor, currency)


def test_decimal_arithmetic_has_no_float_error():
    # float("0.29") * 100 == 28.999999999999996
    assert parse_price("$0.29").minor == 29
    assert parse_price("₹1,23,456.07").minor == 12345607


@pytest.mark.parametrize(
    ("text", "minor"),
    [("-₹200", -20000), (f"{MINUS}$5.00", -500), ("(₹200)", -20000), ("Discount: - €3", -300)],
)
def test_negative_amounts(text, minor):
    assert parse_price(text).minor == minor


@pytest.mark.parametrize("text", ["Free", "FREE", "Delivery: free"])
def test_free(text):
    parsed = parse_price(text)
    assert (parsed.kind, parsed.minor) == ("free", 0)


@pytest.mark.parametrize(
    ("text", "low", "high", "currency"),
    [
        (f"₹499 {EN_DASH} ₹999", 49900, 99900, "INR"),
        ("$10-$20", 1000, 2000, "USD"),
        ("€5 to €8", 500, 800, "EUR"),
        ("₹499-999", 49900, 99900, "INR"),
    ],
)
def test_ranges(text, low, high, currency):
    parsed = parse_price(text)
    assert (parsed.kind, parsed.minor, parsed.max_minor, parsed.currency) == (
        "range",
        low,
        high,
        currency,
    )


def test_range_with_two_currencies_is_rejected():
    assert parse_price("$10 - €20") is None


def test_struck_through_price_from_the_dom():
    parsed = parse_price("₹1,499 ₹2,999 50% off", struck_texts=["₹2,999"])
    assert (parsed.minor, parsed.struck_minor) == (149900, 299900)


@pytest.mark.parametrize(
    "text", ["MRP ₹2,999 ₹1,499", "Was $29.99 now $14.99", "List price: €30 €15"]
)
def test_labelled_old_price(text):
    parsed = parse_price(text)
    assert parsed.struck_minor is not None
    assert parsed.minor < parsed.struck_minor


def test_two_unlabelled_prices_are_ambiguous():
    assert parse_price("₹1,499 ₹2,999") is None


@pytest.mark.parametrize("text", ["₹1,2345", "$1,499.999", "€1,2,3", "₹12,3,456"])
def test_malformed_numbers_are_rejected(text):
    assert parse_price(text) is None


@pytest.mark.parametrize("text", ["50% off", "Qty 2", "only 3 left", "2 hrs 30 min", "", "  "])
def test_non_prices(text):
    assert parse_price(text) is None


def test_bare_number_needs_a_default_currency():
    assert parse_price("1,499") is None
    parsed = parse_price("1,499", default_currency="INR")
    assert (parsed.minor, parsed.currency) == (149900, "INR")


def test_find_amounts_lists_every_amount_in_order():
    text = f"Subtotal ₹1,499; Convenience fee ₹49; Discount {MINUS}₹100; 2 items"
    assert [(a.minor, a.currency) for a in find_amounts(text)] == [
        (149900, "INR"),
        (4900, "INR"),
        (-10000, "INR"),
    ]


def test_quantity_before_a_prefixed_price_is_not_read_as_a_suffix_price():
    # "1 ₹49" must be "qty 1, ₹49", not "₹1" followed by a stray 49 (found by the walker).
    assert [a.minor for a in find_amounts(f"Gift card sleeve {TIMES} 1 ₹49")] == [4900]
    assert parse_price(f"Notebook Set {TIMES} 1 ₹199").minor == 19900
