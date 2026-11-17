"""Build the commerce extension (price ledger, cart, default add-ons, terms) step by step.

The ledger records what was *shown*, where it first appeared, and whether the walker could
have avoided it. Judging whether that adds up to drift is the detectors' job (Phase 4).
"""

from __future__ import annotations

import re

from tripwire.browser.price_parse import find_amounts, parse_price
from tripwire.browser.ui_inventory import PageObservation
from tripwire.schemas.common import Money
from tripwire.schemas.trace import AddOn, CartItem, Commerce, PriceLine, PriceRole, TermsNotice

_ROLES: list[tuple[PriceRole, re.Pattern[str]]] = [
    (PriceRole.TOTAL, re.compile(r"\b(total|payable|due|amount to pay|grand)\b", re.I)),
    (PriceRole.TAX, re.compile(r"\b(tax|gst|vat)\b", re.I)),
    (PriceRole.SHIPPING, re.compile(r"\b(delivery|shipping|postage)\b(?!\s+protection)", re.I)),
    (PriceRole.DISCOUNT, re.compile(r"\b(discount|coupon|saving|promo|offer)\b", re.I)),
    (PriceRole.FEE, re.compile(r"\b(fee|charge|surcharge|handling)\b", re.I)),
]
_QTY = re.compile(r"^(?P<name>.*?)\s*[\u00d7xX]\s*(?P<qty>\d+)\b")
_MONTHS = r"jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
_DATE = re.compile(
    rf"\b(\d{{1,2}}\s+({_MONTHS})[a-z]*\s+\d{{4}}|({_MONTHS})[a-z]*\s+\d{{1,2}},?\s+\d{{4}}"
    rf"|\d{{1,2}}/\d{{1,2}}/\d{{2,4}})\b",
    re.IGNORECASE,
)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" :-" + chr(0x2013))


def _without_amounts(text: str) -> str:
    for amount in reversed(find_amounts(text)):
        text = text[: amount.start] + " " + text[amount.end :]
    return _clean(re.sub(r"\(.*?\)", " ", text))


def item_name(label: str) -> str:
    m = _QTY.match(label)
    return _clean(m["name"] if m else label)


def role_of(label: str, item_names: set[str]) -> PriceRole:
    if item_name(label).lower() in item_names:
        return PriceRole.ITEM
    for role, pattern in _ROLES:
        if pattern.search(label):
            return role
    return PriceRole.ITEM if _QTY.match(label) else PriceRole.OTHER


class CommerceRecorder:
    def __init__(self) -> None:
        self.lines: dict[tuple[str, int], PriceLine] = {}
        self.cart: dict[str, CartItem] = {}
        self.addons: dict[str, AddOn] = {}
        self.terms: dict[str, TermsNotice] = {}
        self.added: dict[str, int] = {}  # item name (lower) -> qty the walker chose
        self.plan_intent = False  # sign-up flows: the walker chose one unit of the plan

    def record_add(self, name: str, qty: int = 1) -> None:
        key = name.lower()
        self.added[key] = self.added.get(key, 0) + qty

    def observe(self, step_index: int, obs: PageObservation) -> None:
        # Paid checkboxes: the first-seen state is what the page chose for the user.
        for e in obs.elements:
            if e.role not in ("checkbox", "switch") or not e.style.visible:
                continue
            label = e.accessible_name or e.text
            parsed = parse_price(label) if label else None
            if label and parsed and parsed.kind == "amount" and label not in self.addons:
                self.addons[label] = AddOn(
                    label=label,
                    price=Money(minor=parsed.minor, currency=parsed.currency or "INR"),
                    preselected=bool(e.checked),
                    step_index=step_index,
                    element_id=e.id,
                )

        seen_here: set[tuple[str, int]] = set()
        for candidate in obs.prices:
            parsed = candidate.parsed
            if parsed is None or parsed.kind == "range" or candidate.in_control:
                continue
            label = _without_amounts(candidate.row_text)
            if not label:
                continue
            key = (item_name(label).lower(), parsed.minor)
            if key in seen_here:
                continue
            seen_here.add(key)
            self._ledger(step_index, label, key, parsed.minor, parsed.currency or "INR")
            self._cart(step_index, label, parsed.minor, parsed.currency or "INR")

        for t in obs.terms:
            if t.visible and t.text not in self.terms:
                self.terms[t.text] = TermsNotice(
                    step_index=step_index,
                    text=t.text,
                    font_size_px=t.font_size_px,
                    contrast_ratio=t.contrast_ratio,
                    mentions_price=bool(find_amounts(t.text)),
                    mentions_date=bool(_DATE.search(t.text)),
                )

    def _classify(self, label: str) -> tuple[PriceRole, bool]:
        role = role_of(label, set(self.added))
        name = item_name(label).lower()
        addons = [_without_amounts(a).lower() for a in self.addons]
        optional = any(a and (name in a or a in label.lower()) for a in addons)
        if role == PriceRole.ITEM and name not in self.added and not self.plan_intent:
            optional = True  # an item the walker never chose
        return role, not optional

    def _ledger(self, step: int, label: str, key: tuple[str, int], minor: int, currency: str):
        role, mandatory = self._classify(label)
        line = self.lines.get(key)
        if line is not None:
            update: dict = {}
            if step not in line.seen_steps:
                update["seen_steps"] = [*line.seen_steps, step]
            if line.role == PriceRole.OTHER and role != PriceRole.OTHER:
                # First seen on a listing page, recognised later (e.g. once added to the cart).
                update |= {"role": role, "mandatory": mandatory}
            if update:
                self.lines[key] = line.model_copy(update=update)
            return
        self.lines[key] = PriceLine(
            label=label,
            amount=Money(minor=minor, currency=currency),
            role=role,
            mandatory=mandatory,
            first_step=step,
            seen_steps=[step],
        )

    def _cart(self, step: int, label: str, minor: int, currency: str) -> None:
        m = _QTY.match(label)
        if not m:
            return
        name, qty = _clean(m["name"]), int(m["qty"])
        added = self.added.get(name.lower(), 0)
        if not added and self.plan_intent and not self.cart:
            added = 1  # the plan the walker signed up for, one unit
        self.cart[name] = CartItem(
            name=name,
            qty=qty,
            unit_price=Money(minor=minor // qty, currency=currency) if minor % qty == 0 else None,
            qty_added_by_walker=added,
            step_index=step,
        )

    def build(self) -> Commerce | None:
        if not (self.lines or self.cart or self.addons or self.terms):
            return None
        return Commerce(
            price_ledger=list(self.lines.values()),
            cart=list(self.cart.values()),
            default_addons=list(self.addons.values()),
            terms=list(self.terms.values()),
        )
