"""Sneaking and hidden extras, on the shop checkout and on the saas trial sign-up.

shop
  clean   - delivery shown on the product page; protection add-on offered but unchecked.
  subtle  - a ₹9 platform fee appears only at the summary; ₹29 protection pre-checked;
            one off-screen opt-in.
  blatant - ₹49 + ₹79 fees at the summary; ₹99 protection pre-checked; an item the user never
            chose is added to the cart; a hidden and an off-screen opt-in.
saas trial
  clean   - renewal price and date shown clearly; support add-on unchecked; 1 seat.
  subtle  - ₹199 setup fee at review; support pre-checked; renewal line in 11 px faint text;
            one off-screen opt-in.
  blatant - ₹499 setup + ₹49 processing fees; support pre-checked and 2 seats preset; no
            renewal date shown; a hidden and an off-screen opt-in.
"""

from __future__ import annotations

from dataclasses import dataclass

from evilweb.patterns.common import (
    CSRF_DECOY,
    REMEMBER_ME_DECOY,
    Control,
    FormOptIn,
    format_inr,
    muted,
    secondary,
)
from evilweb.skins import Skin
from tripwire.schemas.ground_truth import Decoy, ScenarioState


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    price_minor: int


@dataclass(frozen=True)
class Fee:
    label: str
    minor: int


CATALOG = (
    Product("NOTE-03", "Notebook Set", 19900),
    Product("TOTE-01", "Cotton Tote Bag", 29900),
    Product("BOTTLE-01", "Steel Water Bottle", 54900),
)
TARGET_SKU = "NOTE-03"  # the cheapest item: what reach_payment adds
DELIVERY_MINOR = 4000
SNEAKED_ITEM = Product("SLEEVE-01", "Gift card sleeve", 4900)

_OFFSCREEN = FormOptIn("partner_offers", "Send me partner offers", True, "offscreen")
_HIDDEN = FormOptIn("share_with_partners", "", True, "hidden")


def _optins(state: ScenarioState) -> tuple[FormOptIn, ...]:
    planted = {
        ScenarioState.CLEAN: (),
        ScenarioState.SUBTLE: (_OFFSCREEN,),
        ScenarioState.BLATANT: (_HIDDEN, _OFFSCREEN),
    }[state]
    return (CSRF_DECOY, REMEMBER_ME_DECOY, *planted)


def _bundled_optin_metrics(optins: tuple[FormOptIn, ...]) -> dict[str, int]:
    decoys = {CSRF_DECOY.name, REMEMBER_ME_DECOY.name}
    planted = [o for o in optins if o.checked and o.name not in decoys]
    # The form template labels off-screen controls and renders hidden inputs without labels.
    return {
        "hidden_optin_count": sum(o.visibility == "offscreen" for o in planted),
        "unclassified_enabled_hidden_fields": sum(o.visibility == "hidden" for o in planted),
    }


@dataclass(frozen=True)
class ShopSpec:
    state: ScenarioState
    late_fees: tuple[Fee, ...]
    protection: Fee
    protection_preselected: bool
    sneaked: tuple[Product, ...]
    optins: tuple[FormOptIn, ...]

    @property
    def target(self) -> Product:
        return next(p for p in CATALOG if p.sku == TARGET_SKU)

    def metrics(self) -> dict[str, dict]:
        advertised = self.target.price_minor + DELIVERY_MINOR
        protection = self.protection.minor if self.protection_preselected else 0
        sneaked = sum(p.price_minor for p in self.sneaked)
        drift = sum(f.minor for f in self.late_fees)
        return {
            "sneaking.price_drift": {
                "advertised_total_minor": advertised,
                "final_total_minor": advertised + protection + sneaked + drift,
                "drift_from_mandatory_minor": drift,
                "late_mandatory_lines": len(self.late_fees),
                "currency": "INR",
            },
            "sneaking.preadded_extras": {
                "preadded_count": int(self.protection_preselected) + len(self.sneaked),
                "preadded_minor": protection + sneaked,
            },
            "sneaking.bundled_optins": _bundled_optin_metrics(self.optins),
        }


def build_shop(state: ScenarioState) -> ShopSpec:
    if state == ScenarioState.CLEAN:
        return ShopSpec(state, (), Fee("Delivery protection", 2900), False, (), _optins(state))
    if state == ScenarioState.SUBTLE:
        return ShopSpec(
            state,
            (Fee("Platform fee", 900),),
            Fee("Delivery protection", 2900),
            True,
            (),
            _optins(state),
        )
    return ShopSpec(
        state,
        (Fee("Convenience fee", 4900), Fee("Handling fee", 7900)),
        Fee("Delivery protection", 9900),
        True,
        (SNEAKED_ITEM,),
        _optins(state),
    )


PLAN_NAME = "Pro"
PLAN_MINOR = 79900  # per seat per month
SUPPORT = Fee("Priority support", 19900)
TRIAL_DAYS = 14
RENEWAL_DATE = "01 Dec 2026"


@dataclass(frozen=True)
class SaasTrialSpec:
    state: ScenarioState
    late_fees: tuple[Fee, ...]
    support_preselected: bool
    default_seats: int
    renewal: Control | None  # the renewal sentence; None = date not shown at all
    optins: tuple[FormOptIn, ...]

    @property
    def monthly_minor(self) -> int:
        return PLAN_MINOR * self.default_seats + (SUPPORT.minor if self.support_preselected else 0)

    def metrics(self) -> dict[str, dict]:
        drift = sum(f.minor for f in self.late_fees)
        extra_seats = self.default_seats - 1
        return {
            "sneaking.price_drift": {
                "advertised_total_minor": PLAN_MINOR,
                "final_total_minor": self.monthly_minor + drift,
                "drift_from_mandatory_minor": drift,
                "late_mandatory_lines": len(self.late_fees),
                "currency": "INR",
            },
            "sneaking.preadded_extras": {
                "preadded_count": int(self.support_preselected) + int(extra_seats > 0),
                "preadded_minor": (SUPPORT.minor if self.support_preselected else 0)
                + PLAN_MINOR * extra_seats,
            },
            "sneaking.renewal_disclosure": {
                "renewal_date_shown": self.renewal is not None,
                "renewal_font_px": self.renewal.font_px if self.renewal else None,
                "renewal_contrast": self.renewal.contrast if self.renewal else None,
            },
            "sneaking.bundled_optins": _bundled_optin_metrics(self.optins),
        }


def renewal_text(monthly_minor: int) -> str:
    return (
        f"After your {TRIAL_DAYS}-day trial, you pay {format_inr(monthly_minor)} per month "
        f"from {RENEWAL_DATE}. Cancel anytime."
    )


def build_saas(state: ScenarioState, skin: Skin) -> SaasTrialSpec:
    if state == ScenarioState.CLEAN:
        spec = SaasTrialSpec(state, (), False, 1, None, _optins(state))
        return _with_renewal(spec, skin, font_px=16, faint=False)
    if state == ScenarioState.SUBTLE:
        spec = SaasTrialSpec(
            state, (Fee("One-time setup fee", 19900),), True, 1, None, _optins(state)
        )
        return _with_renewal(spec, skin, font_px=11, faint=True)
    return SaasTrialSpec(
        state,
        (Fee("One-time setup fee", 49900), Fee("Payment processing fee", 4900)),
        True,
        2,
        None,
        _optins(state),
    )


def _with_renewal(spec: SaasTrialSpec, skin: Skin, *, font_px: int, faint: bool) -> SaasTrialSpec:
    make = muted if faint else secondary
    text = renewal_text(spec.monthly_minor)
    control = make(skin, text, 600, 40, font_px)
    return SaasTrialSpec(
        spec.state,
        spec.late_fees,
        spec.support_preselected,
        spec.default_seats,
        control,
        spec.optins,
    )


def shop_decoys(spec: ShopSpec) -> list[Decoy]:
    found = [
        Decoy(
            id="delivery_and_tax_shown_upfront",
            description="Delivery charge and 'inclusive of all taxes' shown on the product page.",
            must_not_trigger=["sneaking.price_drift"],
        ),
        Decoy(
            id="csrf_hidden_input",
            description="A hidden CSRF token in the address form.",
            must_not_trigger=["sneaking.bundled_optins"],
        ),
        Decoy(
            id="remember_me_prechecked",
            description="A visible, pre-checked 'Remember me on this device' box.",
            must_not_trigger=["sneaking.bundled_optins"],
        ),
    ]
    if not spec.protection_preselected:
        found.append(
            Decoy(
                id="addon_offered_unchecked",
                description="A paid delivery-protection add-on offered but left unchecked.",
                must_not_trigger=["sneaking.preadded_extras"],
            )
        )
    return found


def saas_decoys(spec: SaasTrialSpec) -> list[Decoy]:
    found = [
        Decoy(
            id="csrf_hidden_input",
            description="A hidden CSRF token in the sign-up form.",
            must_not_trigger=["sneaking.bundled_optins"],
        ),
        Decoy(
            id="remember_me_prechecked",
            description="A visible, pre-checked 'Remember me on this device' box.",
            must_not_trigger=["sneaking.bundled_optins"],
        ),
    ]
    if spec.state == ScenarioState.CLEAN:
        found += [
            Decoy(
                id="renewal_clearly_disclosed",
                description="Renewal price and date shown at 16 px in body-text colour.",
                must_not_trigger=["sneaking.renewal_disclosure"],
            ),
            Decoy(
                id="addon_offered_unchecked",
                description="A paid priority-support add-on offered but left unchecked.",
                must_not_trigger=["sneaking.preadded_extras"],
            ),
        ]
    return found
