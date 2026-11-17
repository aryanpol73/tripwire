"""Turn the visible text of one price element into integer minor units.

Pure functions: no browser, no floats. Ambiguous text returns None instead of a guess: a
wrong amount silently corrupts every measurement downstream, while a None is a visible gap
the extraction coverage numbers will show.

Supported: INR (₹, Rs., INR), USD ($, US$, USD), EUR (€, EUR), GBP (£, GBP), JPY (¥, JPY);
Indian (1,23,456.50), Western (1,234.56) and European (1.234,56 or 1 234,56) number formats;
negative amounts; "Free"; ranges; crossed-out or labelled old prices.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

# Characters spelled with chr() so no invisible or look-alike character hides in the source.
NBSP, NNBSP, THIN = chr(0xA0), chr(0x202F), chr(0x2009)
MINUS, EN_DASH, EM_DASH = chr(0x2212), chr(0x2013), chr(0x2014)
_GROUP_SPACES = NBSP + NNBSP + THIN

_CURRENCIES = {
    "US$": "USD", "$": "USD", "USD": "USD",
    "€": "EUR", "EUR": "EUR",
    "£": "GBP", "GBP": "GBP",
    "¥": "JPY", "JPY": "JPY",
    "₹": "INR", "RS": "INR", "RS.": "INR", "INR": "INR",
}  # fmt: skip
_EXPONENT = {"JPY": 0}  # minor-unit digits; everything else here uses 2

_CUR = r"(?:US\$|\$|€|£|¥|₹|Rs\.?|INR|USD|EUR|GBP|JPY)"
# A number: digits, possibly with , . or no-break-space separators, ending in a digit.
_NUM = rf"\d(?:[\d,.{_GROUP_SPACES}]*\d)?"
_SPACE = rf"[\s{_GROUP_SPACES}]*"

_AMOUNT_RE = re.compile(
    rf"(?P<neg>[-{MINUS}]{_SPACE}|\()?"
    rf"(?:(?<![A-Za-z])(?P<cur>{_CUR}){_SPACE}(?P<num>{_NUM})"
    rf"|(?<![\d,.])(?P<num2>{_NUM}){_SPACE}(?P<cur2>{_CUR})(?![A-Za-z]|{_SPACE}\d))",
    re.IGNORECASE,
)
_RANGE_RE = re.compile(
    rf"^\s*(?P<c1>{_CUR}){_SPACE}(?P<a>{_NUM})\s*(?:-|{EN_DASH}|{EM_DASH}|to)\s*"
    rf"(?:(?P<c2>{_CUR}){_SPACE})?(?P<b>{_NUM})\s*$",
    re.IGNORECASE,
)
_BARE_RE = re.compile(rf"^\s*(?P<num>{_NUM})\s*$")
_FREE_RE = re.compile(r"\bfree\b", re.IGNORECASE)
_OLD_PRICE_LABEL = re.compile(
    r"(M\.?\s?R\.?\s?P\.?|\bwas|list\s+price|regular\s+price|originally)\s*:?\s*$",
    re.IGNORECASE,
)

PriceKind = Literal["amount", "free", "range"]


@dataclass(frozen=True)
class Amount:
    minor: int  # signed
    currency: str
    start: int
    end: int
    struck: bool = False


@dataclass(frozen=True)
class ParsedPrice:
    kind: PriceKind
    minor: int  # the price; the low end for a range; 0 for free
    currency: str | None
    raw: str
    max_minor: int | None = None  # high end of a range
    struck_minor: int | None = None  # the crossed-out or "was" price, if shown


def currency_code(token: str) -> str:
    return _CURRENCIES[token.upper().replace(" ", "")]


def _valid_groups(groups: list[str], separator: str) -> bool:
    if not all(g.isdigit() for g in groups) or not 1 <= len(groups[0]) <= 3:
        return False
    western = all(len(g) == 3 for g in groups[1:])
    # Indian lakh/crore grouping: 3 digits last, pairs before it (1,23,45,678).
    indian = (
        separator == ","
        and len(groups[-1]) == 3
        and all(len(g) == 2 for g in groups[1:-1])
        and len(groups[0]) <= 2
    )
    return western or indian


def parse_number(text: str) -> Decimal | None:
    """'1,23,456.50' / '1.234,56' / '1 234,56' -> Decimal, or None if the format is invalid."""
    s = "".join(" " if ch in _GROUP_SPACES else ch for ch in text)
    separators = [(i, ch) for i, ch in enumerate(s) if ch in ",. "]
    if not separators:
        return Decimal(s) if s.isdigit() else None
    last_index, last = separators[-1]
    tail = s[last_index + 1 :]
    # A lone , or . followed by 1-2 digits is the decimal point; 3 digits means grouping.
    if last in ",." and len(tail) in (1, 2) and s.count(last) == 1:
        integer, fraction = s[:last_index], tail
    else:
        integer, fraction = s, ""
    group_chars = {ch for ch in integer if ch in ",. "}
    if len(group_chars) > 1:
        return None
    if group_chars:
        sep = group_chars.pop()
        groups = integer.split(sep)
        if not _valid_groups(groups, sep):
            return None
        integer = "".join(groups)
    if not integer.isdigit() or (fraction and not fraction.isdigit()):
        return None
    try:
        return Decimal(f"{integer}.{fraction}" if fraction else integer)
    except InvalidOperation:
        return None


def to_minor(value: Decimal, currency: str) -> int | None:
    scaled = value * (10 ** _EXPONENT.get(currency, 2))
    return int(scaled) if scaled == scaled.to_integral_value() else None


def find_amounts(text: str, struck_texts: Iterable[str] = ()) -> list[Amount]:
    """Every currency-marked amount in the text, in order. Malformed numbers are skipped."""
    struck_values = {(abs(a.minor), a.currency) for s in struck_texts for a in find_amounts(s) if s}
    found = []
    for m in _AMOUNT_RE.finditer(text):
        number = parse_number(m.group("num") or m.group("num2"))
        if number is None:
            continue
        currency = currency_code(m.group("cur") or m.group("cur2"))
        minor = to_minor(number, currency)
        if minor is None:
            continue
        neg = m.group("neg") or ""
        negative = neg.startswith("(") and text[m.end() : m.end() + 1] == ")"
        negative = negative or neg[:1] in ("-", MINUS)
        if negative:
            minor = -minor
        labelled = bool(_OLD_PRICE_LABEL.search(text[max(0, m.start() - 20) : m.start()]))
        struck = labelled or (abs(minor), currency) in struck_values
        found.append(Amount(minor, currency, m.start(), m.end(), struck))
    return found


def _has_malformed_number(text: str) -> bool:
    for m in _AMOUNT_RE.finditer(text):
        if parse_number(m.group("num") or m.group("num2")) is None:
            return True
    return False


def parse_price(
    text: str, *, struck_texts: Iterable[str] = (), default_currency: str | None = None
) -> ParsedPrice | None:
    """Parse one price element's text. None means "not a price" or "ambiguous".

    struck_texts: text of crossed-out elements (<del>, <s>, line-through) inside the same
    element, as seen by the in-page collector. Matching amounts count as the old price.
    """
    if not text or not text.strip():
        return None

    r = _RANGE_RE.match(text)
    if r:
        c1 = currency_code(r["c1"])
        if r["c2"] and currency_code(r["c2"]) != c1:
            return None
        low, high = parse_number(r["a"]), parse_number(r["b"])
        if low is None or high is None or low > high:
            return None
        low_minor, high_minor = to_minor(low, c1), to_minor(high, c1)
        if low_minor is None or high_minor is None:
            return None
        return ParsedPrice("range", low_minor, c1, text, max_minor=high_minor)

    if _has_malformed_number(text):
        return None  # "₹1,2345" must not be half-read as something else

    amounts = find_amounts(text, struck_texts)
    real = [a for a in amounts if not a.struck]
    old = [a for a in amounts if a.struck]
    struck_minor = abs(old[0].minor) if old else None

    if not real and _FREE_RE.search(text):
        return ParsedPrice(
            "free", 0, old[0].currency if old else None, text, struck_minor=struck_minor
        )
    if len(real) == 1:
        a = real[0]
        return ParsedPrice("amount", a.minor, a.currency, text, struck_minor=struck_minor)
    if not real and len(old) == 1:
        # Only a labelled price (for example "MRP ₹999"): that is the price.
        return ParsedPrice("amount", old[0].minor, old[0].currency, text)
    if amounts:
        return None  # several candidates and nothing says which one is real

    bare = _BARE_RE.match(text)
    if bare and default_currency:
        number = parse_number(bare["num"])
        minor = to_minor(number, default_currency) if number is not None else None
        if minor is not None:
            return ParsedPrice("amount", minor, default_currency, text)
    return None
