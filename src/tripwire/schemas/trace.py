"""The Trace: everything a walker observed during one run of one mission on one site.

The walker writes it; detectors only read it. It must be self-contained: a detector never
looks at Playwright or the live page, only at what was measured and saved here.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    AwareDatetime,
    Field,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveInt,
    StringConstraints,
    model_validator,
)

from tripwire.schemas.common import (
    ArtifactPath,
    BoundingBox,
    ContrastRatio,
    Fraction,
    HttpUrl,
    Model,
    Money,
    NonEmptyStr,
)

TRACE_SCHEMA_VERSION = "0.1.0"

MissionName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]


# --- Header ------------------------------------------------------------------------


class SiteType(StrEnum):
    SHOP = "shop"
    NEWS = "news"
    SAAS = "saas"
    OTHER = "other"


class Mode(StrEnum):
    SANDBOX = "sandbox"  # Evil Web: everything is fake, irreversible actions are allowed
    REAL = "real"  # a real site: safety gate denies irreversible actions


class RunStatus(StrEnum):
    COMPLETED = "completed"
    BUDGET_EXCEEDED = "budget_exceeded"
    HANDED_OFF = "handed_off"  # CAPTCHA, login wall or OTP: control went to the human
    BLOCKED = "blocked"  # the site blocked us; we stop, we never evade
    ERROR = "error"


class Budgets(Model):
    """Used for both the limits of a run and what it actually used."""

    steps: NonNegativeInt
    wall_seconds: NonNegativeFloat
    page_loads: NonNegativeInt
    # Integer micro-dollars (1 USD = 1,000,000). One LLM call costs a fraction of a cent,
    # so cents would round it to zero, and floats are not allowed for money.
    llm_spend_usd_micros: NonNegativeInt = 0

    def exceeds(self, limits: Budgets) -> list[str]:
        return [
            name
            for name in ("steps", "wall_seconds", "page_loads", "llm_spend_usd_micros")
            if getattr(self, name) > getattr(limits, name)
        ]


# --- Steps -------------------------------------------------------------------------


class ActionKind(StrEnum):
    NAVIGATE = "navigate"
    CLICK = "click"
    TYPE = "type"
    SCROLL = "scroll"
    WAIT = "wait"
    REJECT_CONSENT = "reject_consent"
    HANDOFF = "handoff"


class Target(Model):
    """How the element acted on was located. Role and visible text survive skin changes;
    the selector is kept for debugging only."""

    selector: str | None = None
    role: str | None = None
    accessible_name: str | None = None
    visible_text: str | None = None


class Action(Model):
    kind: ActionKind
    target: Target | None = None
    value: str | None = None  # what was typed: sandbox test data only, never secrets


class RequestRecord(Model):
    """One network request from the HAR slice of a step. Cookies and tokens are redacted."""

    id: NonEmptyStr
    method: NonEmptyStr
    url: NonEmptyStr
    resource_type: str
    status: int | None = None  # None when no response arrived (for example, blocked)
    timestamp: AwareDatetime
    post_data_redacted: str | None = None
    blocked_by_gate: bool = False


class Style(Model):
    """Computed style, as the browser resolved it, not as the stylesheet declared it."""

    font_size_px: NonNegativeFloat
    color: str  # CSS colour string, e.g. "rgb(17, 17, 17)"
    background_color: str  # effective background after compositing ancestors
    opacity: Fraction
    visible: bool  # false if display:none, visibility:hidden, opacity 0 or zero size


class UiElement(Model):
    """One interactive element as measured at this step."""

    id: NonEmptyStr  # unique within the step, e.g. "e12"
    role: NonEmptyStr
    text: str
    accessible_name: str | None = None
    bbox: BoundingBox
    style: Style
    contrast_ratio: ContrastRatio | None = None  # None when unmeasurable (image backgrounds)
    checked: bool | None = None  # default state, for checkboxes and toggles
    selected: bool | None = None
    disabled: bool = False
    in_viewport: bool
    z_order: int = 0  # stacking rank on the page: higher is drawn on top
    tree_depth: NonNegativeInt | None = None  # depth in the accessibility tree
    landmark: str | None = None  # enclosing landmark role, e.g. "contentinfo" (footer)


class UiInventory(Model):
    elements: list[UiElement] = Field(default_factory=list)


class OverlayKind(StrEnum):
    BANNER = "banner"
    MODAL = "modal"
    INTERSTITIAL = "interstitial"


class OverlayPurpose(StrEnum):
    CONSENT = "consent"
    NEWSLETTER = "newsletter"
    RETENTION = "retention"
    SURVEY = "survey"
    CONFIRM = "confirm"
    OTHER = "other"


class ControlPurpose(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    SETTINGS = "settings"
    CLOSE = "close"
    CONTINUE = "continue"
    OTHER = "other"


class OverlayControl(Model):
    element_id: NonEmptyStr  # refers to ui.elements[].id in the same step, for its styles
    purpose: ControlPurpose


class Overlay(Model):
    id: NonEmptyStr
    kind: OverlayKind
    purpose: OverlayPurpose
    layer: PositiveInt = 1  # 1 = first layer of a consent dialog, 2 = "manage options", ...
    bbox: BoundingBox
    viewport_coverage: Fraction
    blocks_interaction: bool
    controls: list[OverlayControl] = Field(default_factory=list)


class FormField(Model):
    name: str
    type: NonEmptyStr  # the input type: "email", "checkbox", "hidden", ...
    label: str | None = None
    default_value: str | None = None  # tokens in hidden fields are redacted
    prechecked: bool = False
    hidden: bool = False
    off_screen: bool = False
    required: bool = False
    element_id: str | None = None


class Form(Model):
    id: NonEmptyStr
    action_url: str | None = None
    method: str = "GET"
    fields: list[FormField] = Field(default_factory=list)
    submit_element_id: str | None = None


class Timer(Model):
    element_id: str | None = None
    text: str
    pattern: str  # e.g. "mm:ss" or "only N left"
    seconds_remaining: NonNegativeInt | None = None
    resets_on_reload: bool | None = None  # None until it has been checked


class Step(Model):
    index: NonNegativeInt
    timestamp: AwareDatetime
    action: Action
    url_before: str | None = None  # None for the very first navigation
    url_after: NonEmptyStr
    page_load: bool  # did this step load a new document? Feeds page-load counts.
    screenshot: ArtifactPath | None = None
    a11y_snapshot: ArtifactPath | None = None
    dom_snapshot: ArtifactPath | None = None
    requests: list[RequestRecord] = Field(default_factory=list)  # the step's HAR slice
    ui: UiInventory = Field(default_factory=UiInventory)
    overlays: list[Overlay] = Field(default_factory=list)
    forms: list[Form] = Field(default_factory=list)
    timers: list[Timer] = Field(default_factory=list)

    @model_validator(mode="after")
    def _element_references_exist(self) -> Self:
        ids = [e.id for e in self.ui.elements]
        if len(set(ids)) != len(ids):
            raise ValueError(f"step {self.index}: duplicate ui element ids")
        known = set(ids)
        refs = [c.element_id for o in self.overlays for c in o.controls]
        refs += [f.submit_element_id for f in self.forms if f.submit_element_id]
        refs += [fld.element_id for f in self.forms for fld in f.fields if fld.element_id]
        refs += [t.element_id for t in self.timers if t.element_id]
        missing = sorted(set(refs) - known)
        if missing:
            raise ValueError(f"step {self.index}: unknown element ids {missing}")
        return self


# --- Journeys --------------------------------------------------------------------


class PathGoal(StrEnum):
    ACCEPT_CONSENT = "accept_consent"
    REJECT_CONSENT = "reject_consent"
    SIGN_UP = "sign_up"
    UNSUBSCRIBE = "unsubscribe"
    CANCEL = "cancel"
    DELETE_ACCOUNT = "delete_account"
    REACH_PAYMENT = "reach_payment"
    OTHER = "other"


class MeasuredPath(Model):
    """A measured journey, e.g. "land -> reject cookies"."""

    name: NonEmptyStr
    goal: PathGoal
    clicks: NonNegativeInt
    page_loads: NonNegativeInt
    step_indices: list[NonNegativeInt] = Field(default_factory=list)
    # False when measured structurally from the page instead of performed. On real sites the
    # accept path is never executed (ETHICS rule 6), so it is always executed=false there.
    executed: bool = True
    completed: bool = True
    exit_channel: Literal["web", "phone", "email", "chat"] = "web"


class IntentGoal(StrEnum):
    REJECT_CONSENT = "reject_consent"
    UNSUBSCRIBE = "unsubscribe"
    CANCEL = "cancel"
    DELETE_ACCOUNT = "delete_account"


class Intent(Model):
    """A user goal the walker tried, whether it worked, and the cheapest path it found."""

    goal: IntentGoal
    success: bool
    cheapest_path: str | None = None  # a paths[].name

    @model_validator(mode="after")
    def _success_needs_a_path(self) -> Self:
        if self.success and not self.cheapest_path:
            raise ValueError(f"intent {self.goal} succeeded but names no cheapest_path")
        return self


# --- Commerce extension (reach_payment mission only) ---------------------------------


class PriceRole(StrEnum):
    ITEM = "item"
    TAX = "tax"
    SHIPPING = "shipping"
    FEE = "fee"
    DISCOUNT = "discount"
    TOTAL = "total"
    OTHER = "other"


class PriceLine(Model):
    label: NonEmptyStr
    amount: Money
    role: PriceRole
    mandatory: bool  # false for optional extras the user can decline
    first_step: NonNegativeInt  # where this label and amount first appeared
    seen_steps: list[NonNegativeInt] = Field(default_factory=list)


class CartItem(Model):
    name: NonEmptyStr
    sku: str | None = None
    qty: PositiveInt
    unit_price: Money | None = None
    qty_added_by_walker: NonNegativeInt  # how many of these the walker itself added
    step_index: NonNegativeInt  # the step where this cart state was observed


class AddOn(Model):
    label: NonEmptyStr
    price: Money | None = None
    preselected: bool
    step_index: NonNegativeInt
    element_id: str | None = None


class Commerce(Model):
    price_ledger: list[PriceLine] = Field(default_factory=list)
    cart: list[CartItem] = Field(default_factory=list)
    default_addons: list[AddOn] = Field(default_factory=list)


# --- Notes -------------------------------------------------------------------------


class NoteKind(StrEnum):
    PAGE_INSTRUCTION = "page_instruction"  # page text that tried to instruct the agent
    HANDOFF = "handoff"  # CAPTCHA, login or OTP
    SAFETY_BLOCK = "safety_block"
    BUDGET = "budget"
    INFO = "info"


class Note(Model):
    kind: NoteKind
    step_index: NonNegativeInt | None = None
    message: NonEmptyStr


# --- The Trace -------------------------------------------------------------------


class Trace(Model):
    schema_version: Literal["0.1.0"] = TRACE_SCHEMA_VERSION
    run_id: NonEmptyStr
    site_url: HttpUrl
    site_type: SiteType
    mission: MissionName
    mode: Mode
    scenario_id: str | None = None  # Evil Web scenario, sandbox runs only
    started_at: AwareDatetime
    ended_at: AwareDatetime
    status: RunStatus
    budget_limits: Budgets
    budgets_used: Budgets
    steps: list[Step]
    paths: list[MeasuredPath] = Field(default_factory=list)
    intents: list[Intent] = Field(default_factory=list)
    commerce: Commerce | None = None
    notes: list[Note] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.ended_at < self.started_at:
            raise ValueError("ended_at is before started_at")

        over = self.budgets_used.exceeds(self.budget_limits)
        if over and self.status != RunStatus.BUDGET_EXCEEDED:
            raise ValueError(f"budgets exceeded ({', '.join(over)}) but status is {self.status}")

        for position, step in enumerate(self.steps):
            if step.index != position:
                raise ValueError(f"step at position {position} has index {step.index}")

        request_ids = [r.id for s in self.steps for r in s.requests]
        if len(set(request_ids)) != len(request_ids):
            raise ValueError("request ids must be unique across the trace")

        path_names = [p.name for p in self.paths]
        if len(set(path_names)) != len(path_names):
            raise ValueError("path names must be unique")
        for path in self.paths:
            self._check_steps(path.step_indices, f"path {path.name!r}")
            if path.step_indices != sorted(set(path.step_indices)):
                raise ValueError(f"path {path.name!r}: step indices must be increasing")

        for intent in self.intents:
            if intent.cheapest_path and intent.cheapest_path not in path_names:
                raise ValueError(f"intent {intent.goal}: unknown path {intent.cheapest_path!r}")

        self._check_steps((n.step_index for n in self.notes if n.step_index is not None), "note")
        if self.commerce:
            c = self.commerce
            self._check_steps((p.first_step for p in c.price_ledger), "price line")
            self._check_steps((i for p in c.price_ledger for i in p.seen_steps), "price line")
            self._check_steps((i.step_index for i in c.cart), "cart item")
            self._check_steps((a.step_index for a in c.default_addons), "add-on")
        return self

    def _check_steps(self, indices: Iterable[int], owner: str) -> None:
        for index in indices:
            if index >= len(self.steps):
                raise ValueError(f"{owner} refers to missing step {index}")
